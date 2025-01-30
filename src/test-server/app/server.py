
from starlette.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
import json
import ssl

app = FastAPI()
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain('/code/app/cert.pem', keyfile='/code/app/key.pem')
app.add_middleware(HTTPSRedirectMiddleware)

idrac_sse_json = """
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
idrac_sse_json = json.loads(idrac_sse_json)

idrac_json = """
{
   "@odata.context":"/redfish/v1/$metadata#Manager.Manager",
   "@odata.id":"/redfish/v1/Managers/iDRAC.Embedded.1",
   "@odata.type":"#Manager.v1_19_1.Manager"
}
"""
idrac_json = json.loads(idrac_json)

async def generator():
    for i in range(10):
        yield json.dumps ({"event_id": i, "data": f"{i + 1} chunk of data", "is_final_event": i == 9}) + '\n' 
        await asyncio.sleep(1)

async def idrac_generator():
    for i in range(10):
        yield json.dumps (idrac_sse_json) + '\n' 
        await asyncio.sleep(10)

@app.get('/redfish/v1/Managers/iDRAC.Embedded.1')
def managers():
    return JSONResponse(content=idrac_json)

@app.get('/redfish/v1/SSE')
def sse(filter: str = None):
    return EventSourceResponse(idrac_generator())