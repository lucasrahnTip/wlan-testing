#!/usr/bin/perl

# Query test-bed orchestator URL to see if there are new tests for us to run.
# This is expected to be run on the test-bed controller (not orchestrator)
# One of these processes will run for each test bed controlled by the controller.

use strict;
use warnings;
use Getopt::Long;

my $user = "";
my $passwd = "";
my $jfrog_user = "cicd_user";
my $jfrog_passwd = "";
my $url = "";
my $next_info = "__next_test.txt";
my $help = 0;

my $usage = qq($0
  [--jfrog_user { jfrog user (default: cicd_user) }
  [--jfrog_passwd { jfrog password }
  [--user { for accessing URL }
  [--passwd { for accessing URL }
  [--url { test-orchestrator URL for this test bed }
  [--next_info { output text file containing info about the next test to process }

Example:
$0 --user to_user --passwd secret --jfrog_user cicd_user --jfrog_passwd secret2 \
   --url https://tip.cicd.mycloud.com/testbed-ferndale-01/

);

GetOptions
(
  'jfrog_user=s'           => \$jfrog_user,
  'jfrog_passwd=s'         => \$jfrog_passwd,
  'user=s'                 => \$user,
  'passwd=s'               => \$passwd,
  'url=s'                  => \$url,
  'next_info=s'            => \$next_info,
  'help|?'                 => \$help,
) || (print($usage) && exit(1));

if ($help) {
  print($usage) && exit(0);
}

if ($jfrog_passwd eq "") {
   print("ERROR:  You must specify jfrog password.\n");
   exit(1);
}

if ($user ne "" && $passwd eq "") {
   print("ERROR:  You must specify a password if specifying a user.\n");
   exit(1);
}

my $i;

my $cuser = "-u $user:$passwd";
if ($user eq "") {
   $cuser = "";
}

my $cmd = "curl $cuser $url";

print ("Calling command: $cmd\n");
my $listing = do_system($cmd);
my @lines = split(/\n/, $listing);
for ($i = 0; $i<@lines; $i++) {
   my $ln = $lines[$i];
   chomp($ln);

   my $fname = "";
   my $name = "";
   my $date = "";

   if ($ln =~ /href=\"(CICD_TEST-.*)\">(.*)<\/a>\s+(.*)\s+\S+\s+\S+/) {
      $fname = $1;
      $name = $2;
      $date = $3;
   }
   elsif ($ln =~ /href=\"(CICD_TEST-.*)\">(.*)<\/a>/) {
      $fname = $1;
   }

   if ($fname ne "") {
      # Grab that test file
      $cmd = "curl --location $cuser -o $next_info $url/$fname";
      do_system($cmd);

      # Read in that file
      my $jurl = "";
      my $jfile = "";
      my $report_to = "";
      my $report_name = "";
      my $swver = "";
      my $fdate = "";
      my $ttype = "";
      my $listing = do_system("cat $next_info");
      my @lines = split(/\n/, $listing);
      for ($i = 0; $i<@lines; $i++) {
         my $ln = $lines[$i];
         chomp($ln);
         if ($ln =~ /^CICD_URL=(.*)/) {
            $jurl = $1;
         }
         elsif ($ln =~ /^CICD_TYPE=(.*)/) {
            $ttype = $1;
         }
         elsif ($ln =~ /^CICD_FILE_NAME=(.*)/) {
            $jfile = $1;
         }
         elsif ($ln =~ /^CICD_RPT_DIR=(.*)/) {
            $report_to = $1;
         }
         elsif ($ln =~ /^CICD_RPT_NAME=(.*)/) {
            $report_name = $1;
         }
         elsif ($ln =~ /^CICD_GITHASH=(.*)/) {
            $swver = $1;
         }
         elsif ($ln =~ /^CICD_FILEDATE=(.*)/) {
            $fdate = $1;
         }
      }

      if ($swver eq "") {
         $swver = $fdate;
      }

      if ($swver eq "") {
         $swver = "$jfile";
      }

      if ($jurl eq "") {
         print("ERROR: No CICD_URL found, cannot download file.\n");
         exit(1);
      }
      if ($jfile eq "") {
         print("ERROR: No CICD_FILE_NAME found, cannot download file.\n");
         exit(1);
      }

      my $cmd = "curl --location -o $jfile -u $jfrog_user:$jfrog_passwd $jurl/$jfile";
      do_system($cmd);

      do_system("rm -f openwrt-*.bin");
      do_system("rm -f *sysupgrade.bin"); # just in case openwrt prefix changes.
      do_system("tar xf $jfile");

      # Next steps here are to put the OpenWrt file on the LANforge system
      my $tb_info = do_system("cat TESTBED_INFO.txt");
      my $tb_dir = "";
      if ($tb_info =~ /TESTBED_DIR=(.*)/g) {
         $tb_dir = $1;
      }

      my $env = do_system(". $tb_dir/test_bed_cfg.bash && env");
      my $lfmgr = "";
      my $serial = "";

      if ($env =~ /LFMANAGER=(.*)/g) {
         $lfmgr = $1;
      }
      else {
         print("ERRROR:  Could not find LFMANAGER in environment, configuration error!\n");
         print("env: $env\n");
         exit(1);
      }

      if ($env =~ /AP_SERIAL=(.*)/g) {
         $serial = $1;
      }
      else {
         print("ERRROR:  Could not find AP_SERIAL in environment, configuration error!\n");
         exit(1);
      }

      my $gmport = "3990";
      my $gmanager = $lfmgr;
      my $scenario = "tip-auto";  # matches basic_regression.bash

      if ($env =~ /GMANAGER=(.*)/g) {
         $gmanager = $1;
      }
      if ($env =~ /GMPORT=(.*)/g) {
         $gmport = $1;
      }

      # and then get it onto the DUT, reboot DUT, re-configure as needed,
      do_system("scp *sysupgrade.bin lanforge\@$lfmgr:tip-$jfile");


      # TODO:  Kill anything using the serial port
      do_system("sudo lsof -t $serial | sudo xargs --no-run-if-empty kill -9");

      # and then kick off automated regression test.
      # Default gateway on the AP should be one of the ports on the LANforge system, so we can use
      # that to scp the file to the DUT, via serial-console connection this controller has to the DUT.
      my $ap_route = do_system("../../lanforge/lanforge-scripts/openwrt_ctl.py --scheme serial --tty $serial --action cmd --value \"ip route show\"");
      my $ap_gw = "";
      if ($ap_route =~ /default via (\S+)/g) {
         $ap_gw = $1;
      }
      if ($ap_gw eq "") {
         print("ERROR:  Could not find default gateway for AP, route info:\n$ap_route\n");
         # Re-apply scenario so the LANforge gateway/NAT is enabled for sure.
         do_system("../../lanforge/lanforge-scripts/lf_gui_cmd.pl --manager $gmanager --port $gmport --scenario $scenario");
         # TODO:  Use power-controller to reboot the AP and retry.

         my $out = do_system("../../lanforge/lanforge-scripts/openwrt_ctl.py --scheme serial --tty $serial --action reboot");
         print ("Reboot DUT to try to recover networking:\n$out\n");
         sleep(15);

         $ap_route = do_system("../../lanforge/lanforge-scripts/openwrt_ctl.py --scheme serial --tty $serial --action cmd --value \"ip route show\"");
         if ($ap_route =~ /default via (\S+)/g) {
            $ap_gw = $1;
         }
         if ($ap_gw eq "") {
            exit(1);
         }
      }

      # TODO: Change this to curl download??
      my $ap_out = do_system("../../lanforge/lanforge-scripts/openwrt_ctl.py --scheme serial --tty $serial --action sysupgrade --value \"lanforge\@$ap_gw:tip-$jfile\"");
      print ("Sys-upgrade results:\n$ap_out\n");
      # TODO:  Verify this (and reboot below) worked.  DUT can get wedged and in that case it will need
      # a power-cycle to continue.

      # System should be rebooted at this point.
      sleep(10); # Give it some more time

      # Re-apply overlay
      $ap_out = do_system("cd $tb_dir/OpenWrt-overlay && tar -cvzf ../overlay_tmp.tar.gz * && scp ../overlay_tmp.tar.gz lanforge\@$lfmgr:tip-overlay.tar.gz");
      print ("Create overlay zip:\n$ap_out\n");
      $ap_out = do_system("../../lanforge/lanforge-scripts/openwrt_ctl.py --scheme serial --tty $serial --action download --value \"lanforge\@$ap_gw:tip-overlay.tar.gz\" --value2 \"overlay.tgz\"");
      print ("Download overlay to DUT:\n$ap_out\n");
      $ap_out = do_system("../../lanforge/lanforge-scripts/openwrt_ctl.py --scheme serial --tty $serial --action cmd --value \"cd / && tar -xzf /tmp/overlay.tgz\"");
      print ("Un-zip overlay on DUT:\n$ap_out\n");
      $ap_out = do_system("../../lanforge/lanforge-scripts/openwrt_ctl.py --scheme serial --tty $serial --action reboot");
      print ("Reboot DUT so overlay takes effect:\n$ap_out\n");

      if ($ttype eq "fast") {
         $ap_out = do_system("cd $tb_dir && DUT_SW_VER=$swver ./run_basic_fast.bash");
      }
      else {
         $ap_out = do_system("cd $tb_dir && DUT_SW_VER=$swver ./run_basic.bash");
      }
      print("Regression $ttype test script output:\n$ap_out\n");

      #When complete, upload the results to the requested location.
      if ($ap_out =~ /Results-Dir: (.*)/g) {
         my $rslts_dir = $1;
         print ("Found results at: $rslts_dir\n");
         do_system("rm -fr /tmp/$report_name");
         do_system("mv $rslts_dir /tmp/$report_name");
         do_system("scp -r /tmp/$report_name $report_to/");
         do_system("echo $fname > /tmp/NEW_RESULTS-$fname");
         do_system("scp /tmp/NEW_RESULTS-$fname $report_to/");
      }

      exit(0);
   }

   #print "$ln\n";
}

exit 0;

sub do_system {
   my $cmd = shift;
   print ">>> $cmd\n";
   return `$cmd`;
}