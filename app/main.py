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
from stamina import retry
from datetime import datetime
import pprint

#logger = logging.getLogger('uvicorn')
#logger.setLevel(logging.DEBUG)

logger = logging.getLogger('idrac-sse')
handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s [%(name)-12s] %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

hosts_file = os.environ.get('HOSTS_FILE', default="app/hosts")
idrac_username = os.environ.get('iDRAC_USERNAME')
idrac_password = os.environ.get('iDRAC_PASSWORD')
otel_receiver = os.environ.get('OTEL_RECEIVER')
http_receiver = os.environ.get('HTTP_RECEIVER')

retry_attempts = 100
retry_initial_wait = 30.0
retry_wait_exp_base = 2
timeout = httpx.Timeout(10.0, read=None)

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

@retry(on=(httpx.HTTPError), attempts=retry_attempts, wait_initial=retry_initial_wait, wait_exp_base=retry_wait_exp_base)
def test_host_connection(host):
    url = "https://%s/redfish/v1/Managers/iDRAC.Embedded.1" % (host)
    logger.debug("Testing connection to %s" % (url))
    response = httpx.get(url, timeout=timeout, verify=False, auth=(idrac_username, idrac_password))
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
        logger.debug(f"Sending event to {endpoint}")
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            response = await client.post(endpoint, 
                                         json=event,
                                         headers={"Content-Type": "application/json"})
            logger.debug(response.json())
        #yield response
    except httpx.TimeoutException:
        logger.error("Request to %s timed out!" % (endpoint))

# This works, non async client. Using httpx instead
# def get_idrac_sse_sseclient():
#     url = "https://169.254.1.1/redfish/v1/SSE?$filter=EventFormatType%20eq%20Event"
#     events = SSEClient(url, headers={'Content-type' : 'application/json'},
#         verify=False,
#         timeout=None,
#         auth=(user, password))
#     for event in events:
#         logger.debug(event)

# async def iter_sse_retrying(client, method, url, auth):
#     last_event_id = ""
#     reconnection_delay = 0.0

#     # `stamina` will apply jitter and exponential backoff on top of
#     # the `retry` reconnection delay sent by the server.
#     @retry(on=httpx.ReadError, attempts=retries)
#     async def _iter_sse():
#         nonlocal last_event_id, reconnection_delay

#         time.sleep(reconnection_delay)

#         headers = {"Accept": "text/event-stream"}

#         if last_event_id:
#             headers["Last-Event-ID"] = last_event_id

#         async with aconnect_sse(client, method, url, headers=headers, auth=auth) as event_source:
#             async for sse in event_source.aiter_sse():
#                 last_event_id = sse.id

#                 if sse.retry is not None:
#                     reconnection_delay = sse.retry / 1000

#                 yield sse

#     return _iter_sse()

@retry(on=(httpx.HTTPError), attempts=retry_attempts, wait_initial=retry_initial_wait, wait_exp_base=retry_wait_exp_base)
async def get_idrac_sse_httpx(host):
    # Set dynamic property for current task that stores the hostname
    asyncio.current_task().hostname = host
    #transport = httpx.AsyncHTTPTransport(retries=999)
    async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
        #url = "https://%s/redfish/v1/SSE?$filter=EventFormatType eq Event" % (host)
        url = "http://127.0.0.1:8000/"
        logger.debug("Opening SSE connection to %s" % (url))
        #async for sse in await iter_sse_retrying(client, "GET", url, (idrac_username, idrac_password)):
        async with aconnect_sse(client, "GET", url, auth=(idrac_username, idrac_password)) as event_source:
        #async with aconnect_sse(client, "GET", url) as event_source:
            async for sse in event_source.aiter_sse():
                if sse.data != None and sse.data != "":
                    logger.debug("Processing SSE event...")
                    event_json = json.loads(sse.data)
                    logger.debug(json.dumps(event_json, indent=4))
                    # Send to OpenTelemetry Collector OTLP HTTP Receiver
                    if otel_receiver != None and otel_receiver != "":
                        logger.debug("DEBUG1")
                        otlp_event = convert_redfish_event_to_otlp(event_json)
                        result = await send_to_endpoint(otlp_event, otel_receiver)

                    # Send to other HTTP endpoint
                    if http_receiver != None and http_receiver != "":
                        logger.debug("DEBUG2")
                        result = await send_to_endpoint(event_json, http_receiver)

                    #yield event_json

def create_task_log_exception(awaitable: Awaitable) -> asyncio.Task:
    async def _log_exception(awaitable):
        try:
            return await awaitable
        except Exception as e:
            logger.exception(e)
    return asyncio.create_task(_log_exception(awaitable))

async def main():
    tasks = [] #List[Task[None]]
    try:
        hosts = []
        with open(hosts_file, 'r') as file:
            # Read each line in the file
            for line in file:
                if line != "":
                    host = line.strip()
                    hosts.append(host)
                    logger.debug("Found host %s in %s" % (host, hosts_file))
    except FileNotFoundError as e:
        logger.error("File not found %s" % (hosts_file))

    for host in hosts:
        con_result = test_host_connection(host)
        if con_result:
            logger.debug("Testing connection to %s result SUCCESS" % (host))
            #async for event in get_idrac_sse_httpx(host):
            #task = create_task(get_idrac_sse_httpx(host), name=host)
            task = create_task_log_exception(get_idrac_sse_httpx(host))
            tasks.append(task)
        else:
            logger.debug("Testing connection to %s result FAILURE" % (host))        

    while tasks:
        done, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done.copy():
            if task.exception() is not None:
                print('Task exited with exception:')
                task.print_stack()
                #print('Rescheduling the task\n')
                #coro, args, kwargs = tasks.pop(task)
                #tasks[asyncio.create_task(coro(*args, **kwargs))] = coro, args, kwargs
            
            task_name = task.get_name()
            task_host = task.hostname
            # Remove task from list
            tasks.pop()
            print(f"Task completed {task_name} for host {task_host}")
            #coro, args, kwargs = tasks.pop(0)
            # create_task(coro)
            await asyncio.sleep(10)
            logger.debug(f"Restarting task {task_name} for host {task_host}")
            task = create_task_log_exception(get_idrac_sse_httpx(task_host))
            tasks.append(task)
        
asyncio.run(main())