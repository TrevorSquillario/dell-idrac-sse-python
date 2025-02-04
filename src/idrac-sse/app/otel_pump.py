import os
import logging
import json
import httpx
from datetime import datetime
import pytz
from mb import StompConnection, topic_event, topic_metric, topic_stat
from models import Stat

otel_receiver = os.environ.get('OTEL_RECEIVER')
tz = os.environ.get("TZINFO")

logger = logging.getLogger(__name__)

timeout = httpx.Timeout(10.0, read=None)
transport = httpx.HTTPTransport(verify=False, retries=10)

stomp_conn = StompConnection(host="activemq", port=61613, user='admin', password='admin', transport=transport, timeout=timeout)

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

otlp_metricrecord_guage = """
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

def convert_utc_to_nano(utc_dt):
    """Converts a UTC datetime object to local time."""
    local_timezone = pytz.timezone(tz)
    local_time = utc_dt.replace(tzinfo=pytz.utc).astimezone(local_timezone)
    logger.debug(f"Converted datetime from UTC {utc_dt} to {tz} {local_time}")
    local_timestamp = local_time.timestamp()
    local_timestamp_nano = int(local_timestamp * 1e9)
    return local_timestamp_nano

def convert_redfish_metric_event_to_otlp(redfish_event):
    """
        Convert Redfish payload to OTLP JSON format 
        https://github.com/open-telemetry/opentelemetry-proto/blob/v1.5.0/examples/metrics.json
    """
    try:
      otlp = json.loads(otlp_metric_json)
      odata_context = redfish_event["@odata.context"]
      odata_type = redfish_event["@odata.type"]
      odata_id = redfish_event["@odata.id"]
      id = redfish_event["Id"]
      name = redfish_event["Name"]
      #report_sequence = redfish_event["ReportSequence"]
      timestamp = redfish_event["Timestamp"]
      #mrd = redfish_event["MetricReportDefinition"]

      server_servicetag = ""
      server_idrac_version = ""
      if redfish_event.get("Oem"):
          server_servicetag = redfish_event.get("Oem").get("Dell").get("ServiceTag")
          server_idrac_version = redfish_event.get("Oem").get("Dell").get("iDRACFirmwareVersion")
      metrics = redfish_event["MetricValues"]
      metrics_count = redfish_event["MetricValues@odata.count"]

      # Generate Stat object to monitor statistics 
      stat = Stat(name="send_metric_count", odata_type=odata_type, event_id=odata_id, event_count=len(metrics))
      stat_metric = convert_stat_to_otlp_metric(stat.toJson())

      resource_attribute = json.loads(otlp_attribute)
      resource_attribute["key"] = "serverServiceTag"
      resource_attribute["value"]["stringValue"] = server_servicetag
      otlp["resourceMetrics"][0]["resource"]["attributes"].append(resource_attribute)

      otlp["resourceMetrics"][0]["scopeMetrics"][0]["scope"]["name"] = "idrac.MetricReport" #odata_context
      otlp["resourceMetrics"][0]["scopeMetrics"][0]["scope"]["version"] = "1.5.0" #odata_type

      for metric in metrics:
          metric_id = metric["MetricId"]
          metric_timestamp_str = metric.get("Timestamp")
          metric_value = metric["MetricValue"]
          #metric_property = metric["MetricProperty"]
          metric_type = metric.get("Oem").get("Dell").get("@odata.type")
          metric_context_id = metric.get("Oem").get("Dell").get("ContextID")
          metric_label = metric.get("Oem").get("Dell").get("Label")
          metric_source = metric.get("Oem").get("Dell").get("Source")
          metric_fqdd = metric.get("Oem").get("Dell").get("FQDD")

          # If timestamp not found in metric use timestamp from event. Used for SerialLog metric report
          if not metric_timestamp_str:
            metric_timestamp_object = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
          else:
            metric_timestamp_object = datetime.strptime(metric_timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ")
          metric_timestamp_nano = convert_utc_to_nano(metric_timestamp_object)

          metricrecord = json.loads(otlp_metricrecord_guage)
          # If ContextID not found use Label. Used for CPURegisters metric report
          if not metric_context_id:
             metric_context_id_strip = metric_label
          else:
            metric_context_id_strip = metric_context_id
          metric_name = f"{metric_context_id_strip}_{metric_id}"
          # Create valid metric name for Prometheus
          replace_chars = [".", ":", " "]
          for c in replace_chars:
              metric_name = metric_name.replace(c, "")
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
      
      return otlp, stat_metric
    except Exception as e:
      logger.error("Error converting Redfish Event to OTLP Format")
      logger.error(json.dumps(redfish_event))
      logger.exception(e)      

def convert_redfish_log_event_to_otlp(redfish_event):
    """
        Convert Redfish payload to OTLP JSON format 
        https://github.com/open-telemetry/opentelemetry-proto/blob/v1.5.0/examples/logs.json
    """
    try:
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

      # Generate Stat object to monitor statistics 
      stat = Stat(name="send_event_count", odata_type=odata_type, event_id=id, event_count=len(events))
      stat_metric = convert_stat_to_otlp_metric(stat.toJson())

      for event in events:
          event_id = event["EventId"]
          event_timestamp_str = event["EventTimestamp"]
          event_timestamp_object = datetime.strptime(event_timestamp_str, "%Y-%m-%dT%H:%M:%S%z")
          event_timestamp_nano = convert_utc_to_nano(event_timestamp_object)

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

      return otlp, stat_metric
    except Exception as e:
      logger.error("Error converting Redfish Event to OTLP Format")
      logger.error(json.dumps(redfish_event))
      logger.exception(e) 

def otlp_send(event, endpoint, sse_type):
    otlp_event = ""
    otlp_endpoint = ""
    if sse_type == "event":
        topic = topic_event
        otlp_event, stat = convert_redfish_log_event_to_otlp(event)
    elif sse_type == "metric":
        topic = topic_metric
        otlp_event, stat = convert_redfish_metric_event_to_otlp(event)

    logger.info(f"Sending event to kafka topic {topic}")
    logger.debug(json.dumps(otlp_event, indent=4))
    stomp_conn._connect(transport=transport, timeout=timeout)
    stomp_conn.send(body=json.dumps(otlp_event), destination=topic) 
    stomp_conn.send(body=json.dumps(stat), destination=topic_stat) 

def convert_stat_to_otlp_metric(stat):
    try:
      stat = json.loads(stat)
      otlp = json.loads(otlp_metric_json)
      timestamp = datetime.now()

      resource_attribute = json.loads(otlp_attribute)
      resource_attribute["key"] = "source"
      resource_attribute["value"]["stringValue"] = "idrac-sse"
      otlp["resourceMetrics"][0]["resource"]["attributes"].append(resource_attribute)

      otlp["resourceMetrics"][0]["scopeMetrics"][0]["scope"]["name"] = "idrac.sse.stat" 
      otlp["resourceMetrics"][0]["scopeMetrics"][0]["scope"]["version"] = "1.0.0"

      metric_timestamp = timestamp.timestamp()
      metric_timestamp_nano = int(metric_timestamp * 1e9)

      metricrecord = json.loads(otlp_metricrecord_guage)
      metricrecord["name"] = stat["name"]
      metricrecord["description"] = ""
      datapoint = json.loads(otlp_metricrecord_datapoint)

      datapoint["timeUnixNano"] = metric_timestamp_nano
      metric_value_float = 0 
      try:
          metric_value_float = float(stat["event_count"])
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
    except Exception as e:
      logger.error("Error converting Redfish Event to OTLP Format")
      logger.error(stat)
      logger.exception(e)
