
from starlette.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
import json
import ssl
import logging
from fastapi import Request

logger = logging.getLogger('uvicorn')
logger.setLevel(logging.DEBUG)

app = FastAPI()
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain('/code/app/cert.pem', keyfile='/code/app/key.pem')
app.add_middleware(HTTPSRedirectMiddleware)

idrac_sse_log_json = """
{
    "@odata.context": "/redfish/v1/$metadata#Event.Event",
    "@odata.id": "/redfish/v1/EventService/Events/12/redfish/v1/EventService/Events/12",
    "@odata.type": "#Event.v1_5_0.Event",
    "Events": [
        {
            "EventId": "2241",
            "EventTimestamp": "2025-01-29T23:26:31-0600",
            "EventType": "Alert",
            "MemberId": "207",
            "Message": "CPU 1 has a thermal trip (over-temperature) event.",
            "MessageArgs": [
                "1"
            ],
            "MessageArgs@odata.count": 1,
            "MessageId": "IDRAC.2.9.CPU0001",
            "MessageSeverity": "Critical",
            "Severity": "Critical"
        },
        {
            "EventId": "2241",
            "EventTimestamp": "2025-01-29T23:26:31-0600",
            "EventType": "Alert",
            "MemberId": "207",
            "Message": "CPU 1 has a thermal trip (over-temperature) event.",
            "MessageArgs": [
                "1"
            ],
            "MessageArgs@odata.count": 1,
            "MessageId": "IDRAC.2.9.CPU0001",
            "MessageSeverity": "Critical",
            "Severity": "Critical"
        }
    ],
    "Id": "12",
    "Name": "Event Array",
    "Oem": {
        "Dell": {
            "@odata.type": "#DellEvent.v1_0_0.DellEvent",
            "ServerHostname": "r660-ubuntu22"
        }
    }
}
"""
idrac_sse_log_json = json.loads(idrac_sse_log_json)

idrac_sse_metric_json = """
{
    "@odata.type": "#MetricReport.v1_5_0.MetricReport",
    "@odata.context": "/redfish/v1/$metadata#MetricReport.MetricReport",
    "@odata.id": "/redfish/v1/TelemetryService/MetricReports/ThermalSensor",
    "Id": "ThermalSensor",
    "Name": "ThermalSensor Metric Report",
    "ReportSequence": "802",
    "Timestamp": "2025-02-01T00:39:38.000Z",
    "MetricReportDefinition": {
        "@odata.id": "/redfish/v1/TelemetryService/MetricReportDefinitions/ThermalSensor"
    },
    "MetricValues": [
        {
            "MetricId": "TemperatureReading",
            "Timestamp": "2025-02-01T00:39:36.000Z",
            "MetricValue": "42",
            "MetricProperty": "/redfish/v1/Dell/Systems/System.Embedded.1/DellNumericSensor/iDRAC.Embedded.1_0x23_SystemBoardExhaustTemp#CurrentReading",
            "Oem": {
                "Dell": {
                    "@odata.type": "#DellMetricReportValue.v1_0_1.DellMetricReportValue",
                    "ContextID": "System Board Exhaust Temp",
                    "Label": "System Board Exhaust Temp TemperatureReading",
                    "Source": "rawsensor",
                    "FQDD": "iDRAC.Embedded.1#SystemBoardExhaustTemp"
                }
            }
        },
        {
            "MetricId": "TemperatureReading",
            "Timestamp": "2025-02-01T00:39:34.000Z",
            "MetricValue": "20",
            "MetricProperty": "/redfish/v1/Dell/Systems/System.Embedded.1/DellNumericSensor/iDRAC.Embedded.1_0x23_SystemBoardInletTemp#CurrentReading",
            "Oem": {
                "Dell": {
                    "@odata.type": "#DellMetricReportValue.v1_0_1.DellMetricReportValue",
                    "ContextID": "System Board Inlet Temp",
                    "Label": "System Board Inlet Temp TemperatureReading",
                    "Source": "rawsensor",
                    "FQDD": "iDRAC.Embedded.1#SystemBoardInletTemp"
                }
            }
        }
    ],
    "MetricValues@odata.count": 2,
    "Oem": {
        "Dell": {
            "@odata.type": "#DellMetricReport.v1_0_0.DellMetricReport",
            "ServiceTag": "6VQS5X3",
            "MetricReportDefinitionDigest": "0aa43bc2de9f69861a5c902805132759abec59a41b2f65687fabe311b6d1f1ed",
            "iDRACFirmwareVersion": "7.10.90.00"
        }
    }
}
"""
idrac_sse_metric_json = json.loads(idrac_sse_metric_json)

idrac_json = """
{
   "@odata.context":"/redfish/v1/$metadata#Manager.Manager",
   "@odata.id":"/redfish/v1/Managers/iDRAC.Embedded.1",
   "@odata.type":"#Manager.v1_19_1.Manager"
}
"""
idrac_json = json.loads(idrac_json)

async def generator():
    for i in range(100):
        yield json.dumps ({"event_id": i, "data": f"{i + 1} chunk of data", "is_final_event": i == 9}) + '\n' 
        await asyncio.sleep(1)

async def idrac_generator(event_type):
    for i in range(10):
        if event_type == "Event":
            yield json.dumps (idrac_sse_log_json) + '\n' 
        else:
            yield json.dumps (idrac_sse_metric_json) + '\n' 
        await asyncio.sleep(10)

@app.get('/redfish/v1/Managers/iDRAC.Embedded.1')
def managers():
    return JSONResponse(content=idrac_json)

@app.get('/redfish/v1/SSE')
def sse(request: Request):
    filter = request.query_params.get('$filter', None)
    if filter:
        event_type = filter.split(" ")[-1]
        logger.debug(f"Detected event type: {event_type}")
    return EventSourceResponse(idrac_generator(event_type))