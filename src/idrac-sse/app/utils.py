import asyncio
import httpx
from asyncio import Task, create_task
from typing import List, Awaitable
import logging
import otel_pump

logger = logging.getLogger(__name__)

def create_task_log_exception(awaitable: Awaitable) -> asyncio.Task:
    async def _log_exception(awaitable):
        try:
            return await awaitable
        except Exception as e:
            logger.exception(e)
    return asyncio.create_task(_log_exception(awaitable))

def send_to_endpoint(event, endpoint, transport, timeout):
    logger.info(f"Sending event to {endpoint}")
    try:
        with httpx.Client(transport=transport, timeout=timeout) as client:
            response = client.post(endpoint, 
                                            json=event,
                                            headers={"Content-Type": "application/json"})
            logger.debug(f"Endpoint {endpoint} response status code {response.status_code}")
            logger.debug(f"Endpoint {endpoint} response json {response.json()}")
            if response.status_code == 200:
                return True
            else:
                # Throw exception on status codes > 200
                # * You don't normally need to worry about checking for 200. However, this seems to get triggered on 200
                response.raise_for_status()
    except Exception as e:
        logger.exception(e)