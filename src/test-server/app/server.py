
from starlette.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
import json
import ssl
import os
import logging
import random
import time
from fastapi import Request

logger = logging.getLogger('uvicorn')
logger.setLevel(logging.DEBUG)

app = FastAPI()
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain('/code/app/cert.pem', keyfile='/code/app/key.pem')
app.add_middleware(HTTPSRedirectMiddleware)

# async def simple_generator():
#     for i in range(100):
#         yield json.dumps ({"event_id": i, "data": f"{i + 1} chunk of data", "is_final_event": i == 9}) + '\n' 
#         await asyncio.sleep(1)



def get_files(event_type):
    directory_path = ""
    files = []
    if event_type == "Event":
        directory_path = "app/example_logs"
    else:
        directory_path = "app/example_metrics"

    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        if os.path.isfile(file_path):
            print(f"Found file: {file_path}")
            files.append(file_path)

    return files

async def idrac_generator(event_type):
    for i in range(random.randint(1,1000)):
        files = get_files(event_type)
        file = random.choice(files)
        with open(file) as f:
            idrac_sse_example_json = json.load(f)
            yield json.dumps (idrac_sse_example_json) + '\n'
        await asyncio.sleep(random.randint(1,10))

@app.get('/redfish/v1/Managers/iDRAC.Embedded.1')
def managers():
    idrac_json = """
    {
        "@odata.context":"/redfish/v1/$metadata#Manager.Manager",
        "@odata.id":"/redfish/v1/Managers/iDRAC.Embedded.1",
        "@odata.type":"#Manager.v1_19_1.Manager"
    }
    """
    idrac_json = json.loads(idrac_json)
    return JSONResponse(content=idrac_json)

@app.get('/redfish/v1/SSE')
def sse(request: Request):
    filter = request.query_params.get('$filter', None)
    if filter:
        event_type = filter.split(" ")[-1]
        logger.debug(f"Detected event type: {event_type}")
    return EventSourceResponse(idrac_generator(event_type))