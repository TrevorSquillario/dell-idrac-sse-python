import os
import json
import httpx
import asyncio
from asyncio import Task, create_task
from typing import List, Awaitable
import logging
import logging.config
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
loglevel_str = os.environ.get('LOGLEVEL', default='INFO')
loglevel = getattr(logging, loglevel_str, "INFO")
idrac_username = os.environ.get('iDRAC_USERNAME')
idrac_password = os.environ.get('iDRAC_PASSWORD')
otel_receiver = os.environ.get('iDRAC_SSE_OTEL_RECEIVER')
http_receiver = os.environ.get('iDRAC_SSE_HTTP_RECEIVER')

LOGGING_CONFIG = { 
    'version': 1,
    'formatters': { 
        'standard': { 
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': { 
        'default': { 
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'level': loglevel,
        },
    },
    'loggers': {
        '': {  # root logger
            'handlers': ['default'],
            'level': loglevel,
        },
        'idrac_redfish': {  # root logger
            'handlers': ['default'],
            'level': loglevel,
            'propagate': False
        },
        'mb': {  # root logger
            'handlers': ['default'],
            'level': loglevel,
            'propagate': False
        },
        'otel_pump': {  # root logger
            'handlers': ['default'],
            'level': loglevel,
            'propagate': False
        },
        'utils': {  # root logger
            'handlers': ['default'],
            'level': loglevel,
            'propagate': False
        },
    },
}

# Run once at startup:
logging.config.dictConfig(LOGGING_CONFIG)

logger = logging.getLogger()
#logger.setLevel(getattr(logging, loglevel, "INFO"))

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
            p1 = Process(target=idrac.get_idrac_sse_httpx, args=(host, idrac_username, idrac_password, "log"))
            p1.host = host
            p1.sse_type = "log"
            p2 = Process(target=idrac.get_idrac_sse_httpx, args=(host, idrac_username, idrac_password, "metric"))
            p2.host = host
            p2.sse_type = "metric"
            processes.append(p1)
            processes.append(p2)
            p1.start()
            p2.start()

        while True:
            for i, p in enumerate(processes):
                p.join()
                logger.error(f"Process exited for {p.host} > {p.sse_type} with error code {p.exitcode}, restarting...")
                #p.start()
                px = Process(target=idrac.get_idrac_sse_httpx, args=(p.host, idrac_username, idrac_password, p.sse_type))
                px.host = p.host
                px.sse_type = p.sse_type
                processes.pop(i)
                processes.append(px)
                px.start()
            
            time.sleep(5)


    
    except Exception as e:
        logger.exception(e)
        
if __name__ == '__main__':
    main()