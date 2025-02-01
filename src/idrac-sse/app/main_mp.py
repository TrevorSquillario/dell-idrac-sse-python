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

from multiprocessing import Process, Manager 

import idrac_redfish as idrac
import utils

hosts_file = os.environ.get('HOSTS_FILE', default="app/hosts")
loglevel = os.environ.get('LOGLEVEL')
idrac_username = os.environ.get('iDRAC_USERNAME')
idrac_password = os.environ.get('iDRAC_PASSWORD')
otel_receiver = os.environ.get('OTEL_RECEIVER')
http_receiver = os.environ.get('HTTP_RECEIVER')

logger = logging.getLogger('idrac-sse')
handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s [%(name)-12s] %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(getattr(logging, loglevel, "INFO"))

async def every(__seconds: float, func, *args, **kwargs):
    while True:
        func()
        #func(*args, **kwargs)
        await asyncio.sleep(__seconds)

def get_running_tasks():
    all_tasks = asyncio.all_tasks()
    logger.info("--- RUNNING TASKS ---")
    logger.info(f"Running {len(all_tasks)} Tasks")
    for task in all_tasks:
        hostname = getattr(task, 'hostname', 'None')
        event_type = getattr(task, 'event_type', 'None')
        logger.info(f'Running Task: {task.get_name()}, {hostname}, {event_type}, {task.get_coro()}')

async def main():
    try:
        logger.info(f"Log level: {logger.level}")
        # Log running tasks
        if logger.level == logging.DEBUG:
            asyncio.create_task(every(10, get_running_tasks, None))
        elif logger.level == logging.INFO:
            asyncio.create_task(every(60, get_running_tasks, None))

        tasks = [] #List[Task[None]]
        # Read hosts from file
        try:
            hosts = []
            with open(hosts_file, 'r') as file:
                # Read each line in the file
                for line in file:
                    line = line.strip()
                    if line != "" and not line.startswith("#"):
                        hosts.append(line)
                        logger.info("Found host %s in %s" % (line, hosts_file))
        except FileNotFoundError as e:
            logger.error("File not found %s" % (hosts_file))

        # Monitor tasks
        with Manager() as manager: 
            # Create a queue within the context of the manager 
            q = manager.Queue() 

            # Start SSE task for each host
            for host in hosts:
                #reports = idrac.get_attributes(host, idrac_username, idrac_password)
                #reports_to_enable = ["PowerMetrics", "ThermalMetrics", "ThermalSensor", "Sensor", "SystemUsage", "StorageDiskSMARTData"] 
                #idrac.set_attributes(host, idrac_username, idrac_password, attributes=reports, filter=reports_to_enable, enable=True)
                task1 = utils.create_task_log_exception(idrac.get_idrac_sse_httpx(host=host, sse_type="event", user=idrac_username, passwd=idrac_password))
                task2 = utils.create_task_log_exception(idrac.get_idrac_sse_httpx(host=host, sse_type="metric", user=idrac_username, passwd=idrac_password))
                tasks.append(task1)       
                tasks.append(task2)     
    
                # Create two instances of the Process class, one for each function 
                p1 = Process(target=utils.create_task_log_exception, args=(idrac.ge)t_idrac_sse_httpx(host=host, sse_type="event", user=idrac_username, passwd=idrac_password)) 
                p2 = Process(target=utils.create_task_log_exception, args=(idrac.get_idrac_sse_httpx(host=host, sse_type="metric", user=idrac_username, passwd=idrac_password)))
        
                # Start both processes 
                p1.start() 
                p2.start() 
        
                # Wait for both processes to finish 
                p1.join() 
                p2.join() 


        while tasks:
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                if task.exception() is not None:
                    logger.error('Task exited with exception: ')
                    logger.error(task.print_stack())
                    #print('Rescheduling the task\n')
                    #coro, args, kwargs = tasks.pop(task)
                    #tasks[asyncio.create_task(coro(*args, **kwargs))] = coro, args, kwargs
                
                task_name = task.get_name()
                task_host = task.hostname
                task_event_type = task.event_type
                logger.info(f"Task completed {task_name} for host {task_host}")
                task.cancel()
                tasks.pop()
                await asyncio.sleep(10)
                logger.info(f"Restarting task {task_name} for host {task_host}")
                new_task = utils.create_task_log_exception(idrac.get_idrac_sse_httpx(host=host, sse_type=task.event_type, user=idrac_username, passwd=idrac_password))
                tasks.append(new_task)

    except asyncio.CancelledError:
        logger.info("Task cancelled")
        pass
    except Exception as e:
        logger.exception(e)
        
asyncio.run(main())