import os
import json
import time
import httpx
import logging
import argparse

parser = argparse.ArgumentParser(description='Manage iDRAC Telemetry Settings')
parser.add_argument('-a','--all', help='All', required=False, action='store_true')
parser.add_argument('-r','--report-filter', help='Filter', required=False, default=[])
parser.add_argument('-f','--hosts-file', help='Hosts File', required=False, default="hosts")
parser.add_argument('-e','--enable', help='Enable', required=False, default=True)
parser.add_argument('-x','--export', help='Export', required=False)
args = parser.parse_args()

idrac_username = os.environ.get('iDRAC_USERNAME', default="root")
idrac_password = os.environ.get('iDRAC_PASSWORD')

logger = logging.getLogger('test')
logger.level = logging.DEBUG
consoleHandler = logging.StreamHandler()
logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)

headers = {'content-type': 'application/json'} 
timeout = 15

def get_attributes(host, user, passwd):
    """ 
    Checks the current status of telemetry and creates telemetry_attributes, a list of telemetry attributes
    """
    url = f"https://{host}/redfish/v1/TelemetryService/MetricReportDefinitions"
    headers = {'content-type': 'application/json'}
    response = httpx.get(url, headers=headers, verify=False, auth=(user, passwd))
    if response.status_code != 200:
        logger.error(f"- FAIL, status code for reading attributes is not 200, code is: {response.status_code}")
    try:
        logger.info("- INFO, successfully pulled configuration attributes")
        configurations_dict = json.loads(response.text)
        attributes = configurations_dict.get('Members', {})
        telemetry_attributes = [map['@odata.id'] for map in attributes]
        logger.debug(telemetry_attributes)
    except Exception as e:
        logger.error("- FAIL: detailed error message: {e}")
    return telemetry_attributes

def set_attribute(host, user, passwd, uri, enable: bool):
    url = f"https://{host}{uri}"
    #url = f"https://{host}/redfish/v1/TelemetryService/MetricReports/{report}"
    logger.info(f"Setting attribute {url}")
    # ' { "Schedule":{"RecurrenceInterval":"PT0H2M0S"}}
    response = httpx.patch(url, data=json.dumps({"MetricReportDefinitionEnabled": enable}), headers=headers,
                        verify=False, auth=(user, passwd), timeout=timeout)

    if response.status_code != 200:
        logger.error(f"Failed to set attribute {url} status code is: {response.status_code}")
        logger.debug(str(response))
    else:
        logger.debug(response.json())

def set_attributes(host, user, passwd, attributes, enable: bool, filter = []):
    """
    Uses the RedFish API to set the telemetry enabled attribute to user defined status.
    """
    try:
        # Go to each metric report definition and enable or disable based on input
        for uri in attributes:
            attribute_name = uri.split('/')[-1]
            if len(filter) > 0:
                if attribute_name in filter:
                    set_attribute(host, user, passwd, uri, enable)
            else:
                set_attribute(host, user, passwd, uri, enable)
            time.sleep(2)

        # Enable and disable global telemetry service
        url = f"https://{host}/redfish/v1/TelemetryService"
        logger.info(f"Setting attribute {url}")
        response = httpx.patch(url, data=json.dumps({"ServiceEnabled": enable}), headers=headers,
                                verify=False, auth=(user, passwd))
        
        if response.status_code != 200:
            logger.error("- FAIL, status code for reading attributes is not 200, code is: {}".format(response.status_code))
            logger.debug(str(response))
    except Exception as e:
        logger.error(f"- FAIL: detailed error message: {e}")

def export(host, user, passwd):
    headers = {'content-type': 'application/json'} 

    try:
        if not os.path.exists(args.export):
            os.makedirs(args.export)

        url = f"https://{host}/redfish/v1/TelemetryService/MetricReports"
        headers = {'content-type': 'application/json'}
        response = httpx.get(url, headers=headers, verify=False, auth=(user, passwd))
        if response.status_code != 200:
            logger.error(f"- FAIL, status code for reading attributes is not 200, code is: {response.status_code}")
        try:
            logger.info("- INFO, successfully pulled configuration attributes")
            configurations_dict = json.loads(response.text)
            attributes = configurations_dict.get('Members', {})
            telemetry_attributes = [map['@odata.id'] for map in attributes]
            logger.debug(telemetry_attributes)
        except Exception as e:
            logger.error(f"- FAIL: detailed error message: {e}")
        # Go to each metric report definition and enable or disable based on input
        for uri in telemetry_attributes:
            report_name = uri.split('/')[-1]
            url = f"https://{host}{uri}"
            logger.info(f"Exporting report {url}")
            response = httpx.get(url, headers=headers,
                                verify=False, auth=(user, passwd))

            if response.status_code == 200:
                report_json = response.json()
                f = open(f"{args.export}/{report_name}.json", "w")
                f.write(json.dumps(report_json))
                f.close()
            else:
                logger.error(f"Failed to set attribute {uri} status code is: {response.status_code}")
                logger.debug(str(response))
         
    except Exception as e:
        logger.error(f"- FAIL: detailed error message: {e}")

def main():
    try:
        hosts = []
        with open(args.hosts_file, 'r') as file:
            # Read each line in the file
            for line in file:
                line = line.strip()
                if line != "" and not line.startswith("#"):
                    hosts.append(line)
                    logger.info("Found host %s in %s" % (line, args.hosts_file))
    except FileNotFoundError as e:
        logger.error("File not found %s" % (args.hosts_file))

    for host in hosts:
        reports = get_attributes(host, idrac_username, idrac_password)
        if args.all:
            set_attributes(host, idrac_username, idrac_password, attributes=reports, enable=args.enable) 
        elif len(args.report_filter) > 0:
            set_attributes(host, idrac_username, idrac_password, attributes=reports, filter=args.report_filter, enable=args.enable) 

        if args.export:
            export(host, idrac_username, idrac_password)

main()