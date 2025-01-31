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
import otel
import utils

logger = logging.getLogger('idrac-sse')

timeout = httpx.Timeout(10.0, read=None)
transport = httpx.AsyncHTTPTransport(verify=False, retries=10)

idrac_username = os.environ.get('iDRAC_USERNAME')
idrac_password = os.environ.get('iDRAC_PASSWORD')
otel_receiver = os.environ.get('OTEL_RECEIVER')
http_receiver = os.environ.get('HTTP_RECEIVER')

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

async def send_to_endpoint(event, endpoint):
    logger.info(f"Sending event to {endpoint}")
    try:
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
            response = await client.post(endpoint, 
                                            json=event,
                                            headers={"Content-Type": "application/json"})
            logger.debug(response.status_code)
            logger.debug(response.json())
            if response.status_code == 200:
                return True
            else:
                # Throw exception on status codes > 200
                # * You don't normally need to worry about checking for 200. However, this seems to get triggered on 200
                response.raise_for_status()
    except Exception as e:
        logger.exception(e)

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
                logger.info(f"Setting attribute {url}")
                response = httpx.patch(url, data=json.dumps({"MetricReportDefinitionEnabled": enable}), headers=headers,
                                    verify=False, auth=(user, passwd))
            
                if response.status_code != 200:
                    logger.error(f"Failed to set attribute {uri} status code is: {response.status_code}")
                    logger.debug(str(response))
            
        # Enable and disable global telemetry service
        url = f"https://{host}/redfish/v1/TelemetryService"
        logger.info(f"Setting attribute {url}")
        response = httpx.patch(url, data=json.dumps({"ServiceEnabled": enable}), headers=headers,
                                verify=False, auth=(user, passwd))
        
        if response.status_code != 200:
            logger.error("- FAIL, status code for reading attributes is not 200, code is: {}".format(response.status_code))
            logger.debug(str(response))
    except Exception as e:
        logger.error("- FAIL: detailed error message: {e}")

###
# Exponential Backoff
#   * Wait 10 seconds between each retry starting with 10 seconds, then up to 3600 seconds (1 hour). Stop after 86400 seconds (1 day)
#   * The @retry tenacity decorator only gets triggered if connection is established and Exception is thrown
###
@retry(wait=wait_exponential(multiplier=10, min=10, max=3600), stop=stop_after_delay(86400)) #, reraise=True
async def get_idrac_sse_httpx(host, user, passwd, sse_type: str = "event"):
    # Set dynamic property for current task that stores the hostname
    current_task = asyncio.current_task()
    current_task.hostname = host
    current_task.event_type = sse_type
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
                        logger.info("Processing SSE event...")
                        event_json = json.loads(sse.data)
                        logger.debug(json.dumps(event_json, indent=4))
                        # Send to OpenTelemetry Collector OTLP HTTP Receiver at [otel_collector_address]/v1/logs
                        if otel_receiver != None and otel_receiver != "":
                            logger.info(f"OTEL Receiver Configured: {otel_receiver}")
                            logger.info(f"SSE Event Type: {sse_type}")
                            try: 
                                if sse_type == "event":
                                    otlp_log_event = await otel.convert_redfish_log_event_to_otlp(event_json)
                                    logger.debug(json.dumps(otlp_log_event, indent=4))
                                    otel_receiver_logs = f"{otel_receiver}/v1/logs"
                                    utils.create_task_log_exception(send_to_endpoint(otlp_log_event, otel_receiver_logs))
                                elif sse_type == "metric":
                                    otlp_metric_event = await otel.convert_redfish_metric_event_to_otlp(event_json)
                                    logger.debug(json.dumps(otlp_metric_event, indent=4))
                                    otel_receiver_metrics = f"{otel_receiver}/v1/metrics"
                                    utils.create_task_log_exception(send_to_endpoint(otlp_metric_event, otel_receiver_metrics))
                            except Exception as e:
                                logger.exception(e)
                            
                        # Send to other HTTP endpoint
                        if http_receiver != None and http_receiver != "":
                            result = await send_to_endpoint(event_json, http_receiver)

                        #yield event_json
    else:
        logger.error("Testing connection to %s result FAILURE" % (host)) 