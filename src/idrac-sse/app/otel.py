import json
from asyncio import Task, create_task
from typing import List, Awaitable
import logging
from tenacity import retry, stop_after_attempt, stop_after_delay, wait_exponential
from datetime import datetime

logger = logging.getLogger('idrac-sse')

otlp_log_json = """{
  "resourceLogs": [
    {
      "resource": {
        "attributes": []
      },
      "scopeLogs": [
        {
          "scope": {
            "name": "my.library",
            "version": "1.0.0"
          },
          "logRecords": []
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

otlp_metric_json = """
{
  "resourceMetrics": [
    {
      "resource": {
        "attributes": []
      },
      "scopeMetrics": [
        {
          "scope": {
            "name": "my.library",
            "version": "1.0.0",
            "attributes": []
          },
          "metrics": []
        }
      ]
    }
  ]
}
"""

otlp_metricrecord = """
{
  "name": "my.gauge",
  "description": "I am a Gauge",
  "gauge": {
    "dataPoints": []
  }
}
"""

otlp_metricrecord_datapoint = """
{
  "asDouble": 10,
  "timeUnixNano": "1544712660300000000",
  "attributes": []
}
"""

def convert_redfish_metric_event_to_otlp(redfish_event):
    """
        Convert Redfish payload to OTLP JSON format 
        https://github.com/open-telemetry/opentelemetry-proto/blob/v1.5.0/examples/metrics.json
    """
    otlp = json.loads(otlp_metric_json)
    odata_context = redfish_event["@odata.context"]
    odata_type = redfish_event["@odata.type"]
    odata_id = redfish_event["@odata.id"]
    id = redfish_event["Id"]
    name = redfish_event["Name"]
    report_sequence = redfish_event["ReportSequence"]
    timestamp = redfish_event["Timestamp"]
    mrd = redfish_event["MetricReportDefinition"]

    server_servicetag = redfish_event["Oem"]["Dell"]["ServiceTag"]
    server_idrac_version = redfish_event["Oem"]["Dell"]["iDRACFirmwareVersion"]
    metrics = redfish_event["MetricValues"]
    metrics_count = redfish_event["MetricValues@odata.count"]

    resource_attribute = json.loads(otlp_attribute)
    resource_attribute["key"] = "serverServiceTag"
    resource_attribute["value"]["stringValue"] = server_servicetag
    otlp["resourceMetrics"][0]["resource"]["attributes"].append(resource_attribute)

    otlp["resourceMetrics"][0]["scopeMetrics"][0]["scope"]["name"] = "idrac.MetricReport" #odata_context
    otlp["resourceMetrics"][0]["scopeMetrics"][0]["scope"]["version"] = odata_type

    for metric in metrics:
        metric_id = metric["MetricId"]
        metric_timestamp_str = metric["Timestamp"]
        metric_value = metric["MetricValue"]
        metric_property = metric["MetricProperty"]
        metric_type = metric["Oem"]["Dell"]["@odata.type"]
        metric_context_id = metric["Oem"]["Dell"]["ContextID"]
        metric_label = metric["Oem"]["Dell"]["Label"]
        metric_source = metric["Oem"]["Dell"]["Source"]
        metric_fqdd = metric["Oem"]["Dell"]["FQDD"]

        metric_timestamp_object = datetime.strptime(metric_timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        metric_timestamp = metric_timestamp_object.timestamp()
        metric_timestamp_nano = int(metric_timestamp * 1e9)

        metricrecord = json.loads(otlp_metricrecord)
        metric_context_id_strip = metric_context_id.replace(" ", "")
        metric_name = f"{metric_context_id_strip}_{metric_id}"
        metricrecord["name"] = metric_name
        metricrecord["description"] = metric_label
        datapoint = json.loads(otlp_metricrecord_datapoint)

        datapoint["timeUnixNano"] = metric_timestamp_nano
        metric_value_float = 0
        if metric_value == "Up" or metric_value == "Operational":
            metric_value_float = 1
        else: 
            try:
                metric_value_float = float(metric_value)
            except ValueError:
                logger.debug("Not a float")
        datapoint["asDouble"] = metric_value_float 
        metricrecord["gauge"]["dataPoints"].append(datapoint)
        #log_attribute = json.loads(otlp_attribute)
        #log_attribute["key"] = "messageId"
        #log_attribute["value"]["stringValue"] = event_message_id_base
        #datapoint["attributes"].append(log_attribute)
        otlp["resourceMetrics"][0]["scopeMetrics"][0]["metrics"].append(metricrecord)

    return otlp

def convert_redfish_log_event_to_otlp(redfish_event):
    """
        Convert Redfish payload to OTLP JSON format 
        https://github.com/open-telemetry/opentelemetry-proto/blob/v1.5.0/examples/logs.json
    """
    otlp = json.loads(otlp_log_json)
    odata_context = redfish_event["@odata.context"]
    odata_type = redfish_event["@odata.type"]
    id = redfish_event["Id"]
    server_hostname = redfish_event["Oem"]["Dell"]["ServerHostname"]
    events = redfish_event["Events"]

    resource_attribute = json.loads(otlp_attribute)
    resource_attribute["key"] = "serverHostname"
    resource_attribute["value"]["stringValue"] = server_hostname
    otlp["resourceLogs"][0]["resource"]["attributes"].append(resource_attribute)

    otlp["resourceLogs"][0]["scopeLogs"][0]["scope"]["name"] = "idrac.Event" #odata_context
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
        logrecord["traceId"] = "5B8EFFF798038103D269B633813FC60C" #event_id.encode('utf-8').hex()
        logrecord["spanId"] = "EEE19B7EC3C1B174" #event_member_id.encode('utf-8').hex()
        logrecord["body"]["stringValue"] = event_message
        log_attribute = json.loads(otlp_attribute)
        log_attribute["key"] = "messageId"
        log_attribute["value"]["stringValue"] = event_message_id_base
        logrecord["attributes"].append(log_attribute)
        otlp["resourceLogs"][0]["scopeLogs"][0]["logRecords"].append(logrecord)

    return otlp