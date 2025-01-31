import asyncio
from asyncio import Task, create_task
from typing import List, Awaitable
import logging

logger = logging.getLogger('idrac-sse')

def create_task_log_exception(awaitable: Awaitable) -> asyncio.Task:
    async def _log_exception(awaitable):
        try:
            return await awaitable
        except Exception as e:
            logger.exception(e)
    return asyncio.create_task(_log_exception(awaitable))