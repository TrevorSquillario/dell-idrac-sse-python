
from starlette.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import asyncio
from fastapi import FastAPI
import json

app = FastAPI()

async def generator():
    for i in range(10):
        yield json.dumps ({"event_id": i, "data": f"{i + 1} chunk of data", "is_final_event": i == 9}) + '\n' 
        await asyncio.sleep(1)

@app.get('/')
def root():
    return EventSourceResponse(generator())