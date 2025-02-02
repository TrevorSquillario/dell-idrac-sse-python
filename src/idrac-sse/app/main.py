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

from multiprocessing import Process 

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

def main():
    try:
        logger.info(f"Log level: {logger.level}")
        processes = [] 
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

        # Start SSE task for each host
        for host in hosts:
            #reports = idrac.get_attributes(host, idrac_username, idrac_password)
            #reports_to_enable = ["PowerMetrics", "ThermalMetrics", "ThermalSensor", "Sensor", "SystemUsage", "StorageDiskSMARTData"] 
            #idrac.set_attributes(host, idrac_username, idrac_password, attributes=reports, filter=reports_to_enable, enable=True) 

            # Create two instances of the Process class, one for each function 
            p1 = Process(target=idrac.get_idrac_sse_httpx, args=(host, idrac_username, idrac_password, "event"))
            p2 = Process(target=idrac.get_idrac_sse_httpx, args=(host, idrac_username, idrac_password, "metric"))
            processes.append(p1)
            processes.append(p2)
            p1.start()
            p2.start()

            #for p in processes:
            #    p.join()
    
    except Exception as e:
        logger.exception(e)
        
if __name__ == '__main__':
    main()