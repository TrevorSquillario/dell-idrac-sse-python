import os
import json
import httpx
import asyncio
from asyncio import Task, create_task
from typing import List, Awaitable
import logging
import traceback
import time
from typing import Iterator
#from sseclient import SSEClient
from httpx_sse import connect_sse, aconnect_sse
#from stamina import retry
from tenacity import retry, stop_after_attempt, stop_after_delay, wait_exponential
from datetime import datetime

logger = logging.getLogger('idrac-sse')

timeout = httpx.Timeout(10.0, read=None)
transport = httpx.AsyncHTTPTransport(verify=False, retries=10)

idrac_username = os.environ.get('iDRAC_USERNAME')
idrac_password = os.environ.get('iDRAC_PASSWORD')
otel_receiver = os.environ.get('OTEL_RECEIVER')
http_receiver = os.environ.get('HTTP_RECEIVER')

otlp_json = """{
  "resourceLogs": [
    {
      "resource": {
        "attributes": [
          {
            "key": "service.name",
            "value": {
              "stringValue": "my.service"
            }
          }
        ]
      },
      "scopeLogs": [
        {
          "scope": {
            "name": "my.library",
            "version": "1.0.0"
          },
          "logRecords": [
            
          ]
        }
      ]
    }
  ]
}"""

otlp_attribute = """
{
    "key": "string.attribute",
    "value": {
        "stringValue": "some string"
    }
}
"""

otlp_logrecord = """
{
    "timeUnixNano": "1544712660300000000",
    "observedTimeUnixNano": "1544712660300000000",
    "severityNumber": 10,
    "severityText": "Information",
    "traceId": "5B8EFFF798038103D269B633813FC60C",
    "spanId": "EEE19B7EC3C1B174",
    "body": {
        "stringValue": "Example log record"
    },
    "attributes": []
}
"""

idrac_severity_otlp_severity_number_map = {
    "Critical": 17,
    "Warning": 13,
    "Info": 9,
}

idrac_severity_otlp_severity_text_map = {
    "Critical": "Critical",
    "Warning": "Warning",
    "Info": "Information",
}

def test_host_connection(host):
    url = "https://%s/redfish/v1/Managers/iDRAC.Embedded.1" % (host)
    logger.info("Testing connection to %s" % (url))
    response = httpx.get(url, verify=False, timeout=timeout, auth=(idrac_username, idrac_password))
    # Throw exception on status codes > 200
    response.raise_for_status()
    if response.status_code == 200:
        return True
    else:
        logger.error(response.json())
        return False

async def test_host_connection_async(host):
    url = "https://%s/redfish/v1/Managers/iDRAC.Embedded.1" % (host)
    logger.info("Testing connection to %s" % (url))
    async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
        response = await client.get(url, auth=(idrac_username, idrac_password))
        # Throw exception on status codes > 200
        response.raise_for_status()
        if response.status_code == 200:
            return True
        else:
            logger.error(response.json())
            return False

def convert_redfish_event_to_otlp(redfish_event):
    otlp = json.loads(otlp_json)
    logger.debug(json.dumps(otlp, indent=4))
    odata_context = redfish_event["@odata.context"]
    odata_type = redfish_event["@odata.type"]
    id = redfish_event["Id"]
    server_hostname = redfish_event["Oem"]["Dell"]["ServerHostname"]
    events = redfish_event["Events"]

    resource_attribute = json.loads(otlp_attribute)
    resource_attribute["key"] = "serverHostname"
    resource_attribute["value"]["stringValue"] = server_hostname
    otlp["resourceLogs"][0]["resource"]["attributes"][0] = resource_attribute

    otlp["resourceLogs"][0]["scopeLogs"][0]["scope"]["name"] = odata_context
    otlp["resourceLogs"][0]["scopeLogs"][0]["scope"]["version"] = odata_type

    for event in events:
        event_id = event["EventId"]
        event_timestamp_str = event["EventTimestamp"]
        event_timestamp_object = datetime.strptime(event_timestamp_str, "%Y-%m-%dT%H:%M:%S%z")
        event_timestamp = event_timestamp_object.timestamp()
        event_timestamp_nano = int(event_timestamp * 1e9)
        event_type = event["EventType"]
        event_member_id = event["MemberId"]
        event_message = event["Message"]
        event_message_id = event["MessageId"]
        event_message_id_base = event_message_id.split('.')[-1]
        event_severity = event["Severity"]

        logrecord = json.loads(otlp_logrecord)
        logrecord["timeUnixNano"] = event_timestamp_nano
        logrecord["observedTimeUnixNano"] = event_timestamp_nano
        logrecord["severityNumber"] = idrac_severity_otlp_severity_number_map[event_severity]
        logrecord["severityText"] = idrac_severity_otlp_severity_text_map[event_severity]
        logrecord["traceId"] = event_id.encode('utf-8').hex()
        logrecord["spanId"] = event_member_id.encode('utf-8').hex()
        logrecord["body"]["stringValue"] = event_message
        log_attribute = json.loads(otlp_attribute)
        log_attribute["key"] = "messageId"
        log_attribute["value"]["stringValue"] = event_message_id_base
        logrecord["attributes"].append(log_attribute)
        otlp["resourceLogs"][0]["scopeLogs"][0]["logRecords"].append(logrecord)

    logger.debug(json.dumps(otlp, indent=4))
    return otlp


async def send_to_endpoint(event, endpoint):
    try:
        logger.info(f"Sending event to {endpoint}")
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            response = await client.post(endpoint, 
                                         json=event,
                                         headers={"Content-Type": "application/json"})
            logger.debug(response.json())
        #yield response
    except httpx.TimeoutException:
        logger.error("Request to %s timed out!" % (endpoint))

#@retry(on=(httpx.HTTPError), attempts=retry_attempts, wait_initial=retry_initial_wait, wait_exp_base=retry_wait_exp_base)
###
# Exponential Backoff 
#   * Wait 10 seconds between each retry starting with 10 seconds, then up to 3600 seconds (1 hour). Stop after 86400 seconds (1 day)
#   * The @retry tenacity decorator only gets triggered if an Exception is thrown
###
@retry(wait=wait_exponential(multiplier=10, min=10, max=3600), stop=stop_after_delay(86400))
async def get_idrac_sse_httpx(host, user, passwd, sse_type: str = "event"):
    # Set dynamic property for current task that stores the hostname
    current_task = asyncio.current_task()
    current_task.hostname = host
    logger.info(f"Running Task for host {host}: {current_task}")
    con_result = await test_host_connection_async(host)
    #con_result = test_host_connection(host)
    if con_result:
        logger.info("Testing connection to %s result SUCCESS" % (host))
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
            if sse_type == "event":
                url = "https://%s/redfish/v1/SSE?$filter=EventFormatType eq Event" % (host)
            elif sse_type == "metric":
                url = "https://%s/redfish/v1/SSE?$filter=EventFormatType eq MetricReport" % (host)
            logger.info("Opening SSE connection to %s" % (url))
            async with aconnect_sse(client, "GET", url, auth=(user, passwd)) as event_source:
                # Throw exception on status codes > 200
                event_source.response.raise_for_status()
                async for sse in event_source.aiter_sse():
                    if sse.data != None and sse.data != "":
                        logger.debug("Processing SSE event...")
                        event_json = json.loads(sse.data)
                        logger.debug(json.dumps(event_json, indent=4))
                        # Send to OpenTelemetry Collector OTLP HTTP Receiver
                        if otel_receiver != None and otel_receiver != "":
                            otlp_event = convert_redfish_event_to_otlp(event_json)
                            result = await send_to_endpoint(otlp_event, otel_receiver)

                        # Send to other HTTP endpoint
                        if http_receiver != None and http_receiver != "":
                            result = await send_to_endpoint(event_json, http_receiver)

                        #yield event_json
    else:
        logger.error("Testing connection to %s result FAILURE" % (host)) 

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

def set_attributes(host, user, passwd, attributes, filter, enable: bool):
    """
    Uses the RedFish API to set the telemetry enabled attribute to user defined status.
    """

    headers = {'content-type': 'application/json'} 

    try:
        # Go to each metric report definition and enable or disable based on input
        for uri in attributes:
            attribute_name = uri.split('/')[-1]
            if attribute_name in filter:
                url = f"https://{host}{uri}"
                logger.debug(f"Setting attribute {url}")
                response = httpx.patch(url, data=json.dumps({"MetricReportDefinitionEnabled": enable}), headers=headers,
                                    verify=False, auth=(user, passwd))
            
                if response.status_code != 200:
                    logger.error(f"Failed to set attribute {uri} status code is: {response.status_code}")
                    logger.debug(str(response))
            
        # Enable and disable global telemetry service
        url = f"https://{host}/redfish/v1/TelemetryService"
        logger.debug(f"Setting attribute {url}")
        response = httpx.patch(url, data=json.dumps({"ServiceEnabled": enable}), headers=headers,
                                verify=False, auth=(user, passwd))
        
        if response.status_code != 200:
            logger.error("- FAIL, status code for reading attributes is not 200, code is: {}".format(response.status_code))
            logger.debug(str(response))
    except Exception as e:
        logger.error("- FAIL: detailed error message: {e}")