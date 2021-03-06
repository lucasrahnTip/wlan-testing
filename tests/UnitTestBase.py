#!/usr/bin/python3

import sys

if sys.version_info[0] != 3:
    print("This script requires Python 3")
    exit(1)

for folder in 'py-json', 'py-scripts':
    if folder not in sys.path:
        sys.path.append(f'../lanforge/lanforge-scripts/{folder}')

sys.path.append(f'../libs/lanforge')
sys.path.append(f'../libs/testrails')
sys.path.append(f'../libs/apnos')
sys.path.append(f'../libs/cloudsdk')
sys.path.append(f'../libs')
sys.path.append(f'../tests/test_utility/')

import base64
import urllib.request
from bs4 import BeautifulSoup
import ssl
import subprocess, os
from artifactory import ArtifactoryPath
import tarfile
import paramiko
from paramiko import SSHClient
from scp import SCPClient
import os
import pexpect
from pexpect import pxssh

import paramiko
from scp import SCPClient
import pprint
from pprint import pprint
from os import listdir
import re
import requests
import json
import logging
import datetime
import time
from datetime import date
from shutil import copyfile
import argparse
from unittest.mock import Mock
from lf_tests import *
from ap_plus_sdk import *
from lab_ap_info import *
from JfrogHelper import *
from reporting import Reporting

# For finding files
# https://stackoverflow.com/questions/3207219/how-do-i-list-all-files-of-a-directory
import glob

# external_results_dir=/var/tmp/lanforge

# To run this from your home system to NOLA-01 testbed, use this command. This assumes you have set up an ssh tunnel
# logged to the cicd jumphost that can reach the lab. In separate console to set up the ssh tunnel: ssh -C -L
# 7220:lab-ctlr:22 ubuntu@3.130.51.163 On local machine:
# ./query_ssids.py --testrail-user-id NONE --model ecw5410
# --ap-jumphost-address localhost --ap-jumphost-port 7220 --ap-jumphost-password secret --ap-jumphost-tty /dev/ttyAP1


import testrail_api

from LANforge.LFUtils import *

# if you lack __init__.py in this directory you will not find sta_connect module#

import sta_connect2
from sta_connect2 import StaConnect2
import testrail_api
from testrail_api import TestRail_Client
import eap_connect
from eap_connect import EAPConnect
import cloudsdk
from cloudsdk import CloudSDK
from cloudsdk import CreateAPProfiles
import ap_ssh
from ap_ssh import *

# Import info for lab setup and APs under test
import lab_ap_info
from lab_ap_info import cloud_sdk_models
from lab_ap_info import ap_models
from lab_ap_info import customer_id
from lab_ap_info import cloud_type
from lab_ap_info import test_cases
from lab_ap_info import radius_info

# keep in sync with that below.
def add_base_parse_args(parser):
    parser.add_argument("-b", "--build-id", type=str,
                             help="FW commit ID (latest pending build on dev is default)",
                             default="pending")
    parser.add_argument("--skip-upgrade", type=bool, help="Skip upgrading firmware",
                             default=False)
    parser.add_argument("--force-upgrade", type=bool,
                             help="Force upgrading firmware even if it is already current version",
                             default=False)
    parser.add_argument("-m", "--model", type=str,
                             choices=['ea8300', 'ecw5410', 'ecw5211', 'ec420', 'wf188n', 'eap102', 'None'],
                             help="AP model to be run", required=True)
    parser.add_argument("--equipment-id", type=str,
                             help="AP model ID, as exists in the cloud-sdk.  -1 to auto-detect.",
                             default="-1")
    parser.add_argument("--object-id", type=str,
                             help="Used when querying and deleting individual objects.",
                             default=None)
    parser.add_argument("--customer-id", type=str,
                             help="Specify cloud customer-id, default is 2",
                             default="2")
    parser.add_argument("--testbed", type=str,
                             help="Testbed name, will be prefixed to profile names and similar",
                             default=None)

    parser.add_argument("--sdk-base-url", type=str,
                             help="cloudsdk base url, default: https://wlan-portal-svc.cicd.lab.wlan.tip.build",
                             default="https://wlan-portal-svc.cicd.lab.wlan.tip.build")
    parser.add_argument("--sdk-user-id", type=str, help="cloudsdk user id, default: support@example.conf",
                             default="support@example.com")
    parser.add_argument("--sdk-user-password", type=str, help="cloudsdk user password, default:  support",
                             default="support")

    parser.add_argument("--jfrog-base-url", type=str, help="jfrog base url",
                             default="tip.jFrog.io/artifactory/tip-wlan-ap-firmware")
    parser.add_argument("--jfrog-user-id", type=str, help="jfrog user id",
                             default="tip-read")
    parser.add_argument("--jfrog-user-password", type=str, help="jfrog user password",
                             default="tip-read")

    parser.add_argument("--testrail-base-url", type=str, help="testrail base url",
                             # was os.getenv('TESTRAIL_URL')
                             default="https://telecominfraproject.testrail.com")
    parser.add_argument("--testrail-project", type=str, help="testrail project name",
                             default="opsfleet-wlan")
    parser.add_argument("--testrail-user-id", type=str,
                             help="testrail user id.  Use 'NONE' to disable use of testrails.",
                             default="NONE")
    parser.add_argument("--testrail-user-password", type=str, help="testrail user password",
                             default="password")
    parser.add_argument("--testrail-run-prefix", type=str, help="testrail run prefix",
                             default="prefix-1")
    parser.add_argument("--testrail-milestone", dest="milestone", type=str, help="testrail milestone ID",
                        default="milestone-1")

    parser.add_argument("--lanforge-ip-address", type=str, help="ip address of the lanforge gui",
                             default="127.0.0.1")
    parser.add_argument("--lanforge-port-number", type=str, help="port of the lanforge gui",
                             default="8080")
    parser.add_argument("--lanforge-prefix", type=str, help="LANforge api prefix string",
                             default="sdk")
    parser.add_argument("--lanforge-2g-radio", type=str, help="LANforge 2Ghz radio to use for testing",
                             default="1.1.wiphy0")
    parser.add_argument("--lanforge-5g-radio", type=str, help="LANforge 5Ghz radio to use for testing",
                             default="1.1.wiphy1")

    parser.add_argument("--local_dir", type=str, help="Sanity logging directory",
                             default="logs")
    parser.add_argument("--report-path", type=str, help="Sanity report directory",
                             default="reports")
    parser.add_argument("--report-template", type=str, help="Sanity report template",
                             default="reports/report_template.php")

    parser.add_argument("--eap-id", type=str, help="EAP indentity",
                             default="lanforge")
    parser.add_argument("--ttls-password", type=str, help="TTLS password",
                             default="lanforge")

    parser.add_argument("--ap-ip", type=str, help="AP IP Address, for direct ssh access if not using jumphost",
                             default="127.0.0.1")
    parser.add_argument("--ap-username", type=str, help="AP username",
                             default="root")
    parser.add_argument("--ap-password", type=str, help="AP password",
                             default="root")
    parser.add_argument("--ap-jumphost-address", type=str,
                             help="IP of system that we can ssh in to get serial console access to AP",
                             default=None)
    parser.add_argument("--ap-jumphost-port", type=str,
                             help="SSH port to use in case we are using ssh tunneling or other non-standard ports",
                             default="22")
    parser.add_argument("--ap-jumphost-username", type=str,
                             help="User-ID for system that we can ssh in to get serial console access to AP",
                             default="lanforge")
    parser.add_argument("--ap-jumphost-password", type=str,
                             help="Passwort for system that we can ssh in to get serial console access to AP",
                             default="lanforge")
    parser.add_argument("--ap-jumphost-wlan-testing", type=str, help="wlan-testing repo dir on the jumphost",
                             default="git/wlan-testing")
    parser.add_argument("--ap-jumphost-tty", type=str, help="Serial port for the AP we wish to talk to",
                             default="UNCONFIGURED-JUMPHOST-TTY")

    parser.add_argument('--skip-update-firmware', dest='update_firmware', action='store_false')
    parser.set_defaults(update_firmware=True)

    parser.add_argument('--verbose', dest='verbose', action='store_true')
    parser.set_defaults(verbose=False)


# Keep in sync with that above
def add_base_parse_args_pytest(parser):
    parser.addoption("--default-ap-profile", type=str,
                        help="Default AP profile to use as basis for creating new ones, typically: TipWlan-2-Radios or TipWlan-3-Radios",
                        default="TipWlan-2-Radios")
    parser.addoption("--skip-radius", dest="skip_radius", action='store_true',
                        help="Should we skip the RADIUS configs or not")
    parser.addoption("--skip-profiles", dest="skip_profiles", action='store_true',
                        help="Should we skip applying profiles?")
    parser.addoption("--skip-wpa", dest="skip_wpa", action='store_false',
                        help="Should we skip applying profiles?")
    parser.addoption("--skip-wpa2", dest="skip_wpa2", action='store_false',
                        help="Should we skip applying profiles?")

    parser.addoption("--psk-5g-wpa2", dest="psk_5g_wpa2", type=str,
                        help="Allow over-riding the 5g-wpa2 PSK value.")
    parser.addoption("--psk-5g-wpa", dest="psk_5g_wpa", type=str,
                        help="Allow over-riding the 5g-wpa PSK value.")
    parser.addoption("--psk-2g-wpa2", dest="psk_2g_wpa2", type=str,
                        help="Allow over-riding the 2g-wpa2 PSK value.")
    parser.addoption("--psk-2g-wpa", dest="psk_2g_wpa", type=str,
                        help="Allow over-riding the 2g-wpa PSK value.")

    parser.addoption("--ssid-5g-wpa2", dest="ssid_5g_wpa2", type=str,
                        help="Allow over-riding the 5g-wpa2 SSID value.")
    parser.addoption("--ssid-5g-wpa", dest="ssid_5g_wpa",  type=str,
                        help="Allow over-riding the 5g-wpa SSID value.")
    parser.addoption("--ssid-2g-wpa2", dest="ssid_2g_wpa2", type=str,
                        help="Allow over-riding the 2g-wpa2 SSID value.")
    parser.addoption("--ssid-2g-wpa", dest="ssid_2g_wpa", type=str,
                        help="Allow over-riding the 2g-wpa SSID value.")

    parser.addoption("--mode", dest="mode", choices=['bridge', 'nat', 'vlan'], type=str,
                        help="Mode of AP Profile [bridge/nat/vlan]", default="bridge")

    parser.addoption("--build-id", type=str,
                             help="FW commit ID (latest pending build on dev is default)",
                             default="pending")
    parser.addoption("--skip-upgrade", type=bool, help="Skip upgrading firmware",
                             default=False)
    parser.addoption("--force-upgrade", type=bool,
                             help="Force upgrading firmware even if it is already current version",
                             default=False)
    # --access-points instead
    # parser.addoption("--model", type=str,
    #                          choices=['ea8300', 'ecw5410', 'ecw5211', 'ec420', 'wf188n', 'eap102', 'None'],
    #                          help="AP model to be run", required=True)
    parser.addoption("--equipment-id", type=str,
                             help="AP model ID, as exists in the cloud-sdk.  -1 to auto-detect.",
                             default="-1")
    parser.addoption("--object-id", type=str,
                             help="Used when querying and deleting individual objects.",
                             default=None)
    parser.addoption("--customer-id", type=str,
                             help="Specify cloud customer-id, default is 2",
                             default="2")
    parser.addoption("--testbed", type=str,
                             help="Testbed name, will be prefixed to profile names and similar",
                             default=None)

    parser.addoption("--sdk-base-url", type=str,
                             help="cloudsdk base url, default: https://wlan-portal-svc.cicd.lab.wlan.tip.build",
                             default="https://wlan-portal-svc.cicd.lab.wlan.tip.build")
    parser.addoption("--sdk-user-id", type=str, help="cloudsdk user id, default: support@example.conf",
                             default="support@example.com")
    parser.addoption("--sdk-user-password", type=str, help="cloudsdk user password, default:  support",
                             default="support")

    parser.addoption("--jfrog-base-url", type=str, help="jfrog base url",
                             default="tip.jFrog.io/artifactory/tip-wlan-ap-firmware")
    parser.addoption("--jfrog-user-id", type=str, help="jfrog user id",
                             default="tip-read")
    parser.addoption("--jfrog-user-password", type=str, help="jfrog user password",
                             default="tip-read")

    parser.addoption("--testrail-base-url", type=str, help="testrail base url",
                             # was os.getenv('TESTRAIL_URL')
                             default="https://telecominfraproject.testrail.com")
    parser.addoption("--testrail-project", type=str, help="testrail project name",
                             default="opsfleet-wlan")
    parser.addoption("--testrail-user-id", type=str,
                             help="testrail user id.  Use 'NONE' to disable use of testrails.",
                             default="NONE")
    parser.addoption("--testrail-user-password", type=str, help="testrail user password",
                             default="password")
    parser.addoption("--testrail-run-prefix", type=str, help="testrail run prefix",
                             default="prefix-1")
    parser.addoption("--testrail-milestone", dest="milestone", type=str, help="testrail milestone ID",
                     default="milestone-1")

    parser.addoption("--lanforge-ip-address", type=str, help="ip address of the lanforge gui",
                             default="127.0.0.1")
    parser.addoption("--lanforge-port-number", type=str, help="port of the lanforge gui",
                             default="8080")
    parser.addoption("--lanforge-prefix", type=str, help="LANforge api prefix string",
                             default="sdk")
    parser.addoption("--lanforge-2g-radio", type=str, help="LANforge 2Ghz radio to use for testing",
                             default="1.1.wiphy0")
    parser.addoption("--lanforge-5g-radio", type=str, help="LANforge 5Ghz radio to use for testing",
                             default="1.1.wiphy1")

    parser.addoption("--local_dir", type=str, help="Sanity logging directory",
                             default="logs")
    parser.addoption("--report-path", type=str, help="Sanity report directory",
                             default="reports")
    parser.addoption("--report-template", type=str, help="Sanity report template",
                             default="reports/report_template.php")

    parser.addoption("--eap-id", type=str, help="EAP indentity",
                             default="lanforge")
    parser.addoption("--ttls-password", type=str, help="TTLS password",
                             default="lanforge")

    parser.addoption("--ap-ip", type=str, help="AP IP Address, for direct ssh access if not using jumphost",
                             default="127.0.0.1")
    parser.addoption("--ap-username", type=str, help="AP username",
                             default="root")
    parser.addoption("--ap-password", type=str, help="AP password",
                             default="root")
    parser.addoption("--ap-jumphost-address", type=str,
                             help="IP of system that we can ssh in to get serial console access to AP",
                             default=None)
    parser.addoption("--ap-jumphost-port", type=str,
                             help="SSH port to use in case we are using ssh tunneling or other non-standard ports",
                             default="22")
    parser.addoption("--ap-jumphost-username", type=str,
                             help="User-ID for system that we can ssh in to get serial console access to AP",
                             default="lanforge")
    parser.addoption("--ap-jumphost-password", type=str,
                             help="Passwort for system that we can ssh in to get serial console access to AP",
                             default="lanforge")
    parser.addoption("--ap-jumphost-wlan-testing", type=str, help="wlan-testing repo dir on the jumphost",
                             default="git/wlan-testing")
    parser.addoption("--ap-jumphost-tty", type=str, help="Serial port for the AP we wish to talk to",
                             default="UNCONFIGURED-JUMPHOST-TTY")

    parser.addoption('--skip-update-firmware', dest='update_firmware', action='store_false', default=True)

    parser.addoption('--tip-verbose', dest='verbose', action='store_true', default=False)


class UnitTestBase:

    def __init__(self, log_name, args, reporting=None):
        self.parser = argparse.ArgumentParser(description="Sanity Testing on Firmware Build", parents=[args])

        add_base_parse_args(self.parser)

        self.command_line_args = self.parser.parse_args()

        # cmd line takes precedence over env-vars.
        self.cloudSDK_url = self.command_line_args.sdk_base_url  # was os.getenv('CLOUD_SDK_URL')
        self.local_dir = self.command_line_args.local_dir  # was os.getenv('SANITY_LOG_DIR')
        self.report_path = self.command_line_args.report_path  # was os.getenv('SANITY_REPORT_DIR')
        self.report_template = self.command_line_args.report_template  # was os.getenv('REPORT_TEMPLATE')

        ## TestRail Information
        self.tr_user = self.command_line_args.testrail_user_id  # was os.getenv('TR_USER')
        self.tr_pw = self.command_line_args.testrail_user_password  # was os.getenv('TR_PWD')
        self.milestoneId = self.command_line_args.milestone  # was os.getenv('MILESTONE')
        self.projectId = self.command_line_args.testrail_project  # was os.getenv('PROJECT_ID')
        self.testRunPrefix = self.command_line_args.testrail_run_prefix  # os.getenv('TEST_RUN_PREFIX')

        ##Jfrog credentials
        self.jfrog_user = self.command_line_args.jfrog_user_id  # was os.getenv('JFROG_USER')
        self.jfrog_pwd = self.command_line_args.jfrog_user_password  # was os.getenv('JFROG_PWD')

        ##EAP Credentials
        self.identity = self.command_line_args.eap_id  # was os.getenv('EAP_IDENTITY')
        self.ttls_password = self.command_line_args.ttls_password  # was os.getenv('EAP_PWD')

        ## AP Credentials
        self.ap_username = self.command_line_args.ap_username  # was os.getenv('AP_USER')

        ##LANForge Information
        self.lanforge_ip = self.command_line_args.lanforge_ip_address
        self.lanforge_port = self.command_line_args.lanforge_port_number
        self.lanforge_prefix = self.command_line_args.lanforge_prefix

        self.build = self.command_line_args.build_id

        
        self.logger = logging.getLogger(log_name)

        if not reporting:
            self.hdlr = logging.FileHandler("./logs/test_run.log")
        else:
            self.hdlr = logging.FileHandler(reporting.report_path + "/test_run.log")
        self.formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        self.hdlr.setFormatter(self.formatter)
        self.logger.addHandler(self.hdlr)
        self.logger.setLevel(logging.INFO)

        ####Use variables other than defaults for running tests on custom FW etc

        self.model_id = self.command_line_args.model
        self.equipment_id = self.command_line_args.equipment_id

        ###Get Cloud Bearer Token
        self.cloud: CloudSDK = CloudSDK(self.command_line_args)
        self.bearer = self.cloud.get_bearer(self.cloudSDK_url, cloud_type)
        self.customer_id = self.command_line_args.customer_id

