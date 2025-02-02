import json
import logging
import time
import asyncio
import pandas as pd

logger = logging.getLogger(__name__)

class Stat:
  def __init__(self, odata_type, event_id, event_count):
    self.odata_type = odata_type
    self.event_id = event_id
    self.event_count = event_count

# Creating empty series 
df = pd.DataFrame() 
print("Pandas Series: ", df) 

def add_lister_stats(event):
    stats = []
    
    redfish_event = json.loads(event)
    odata_context = redfish_event["@odata.context"]
    odata_type = redfish_event["@odata.type"]
    odata_id = redfish_event["@odata.id"]
    id = redfish_event["Id"]
    event_count = 0

    if odata_type == "#Event.v1_5_0.Event":
        events = redfish_event["Events"]
        event_count = len(events)

    if odata_type == "#MetricReport.v1_5_0.MetricReport":
        metrics = redfish_event["MetricValues"]
        event_count = len(metrics)

    stat = Stat(odata_type=odata_type, event_id=odata_id, event_count=event_count)

    stat_df = pd.read_json(stat)
    pd.concat([stat_df, df])

async def get_listener_stats():
   while True:
      logger.debug(df.to_string())
      asyncio.sleep(10)
