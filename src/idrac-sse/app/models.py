import json

class Stat:
    def __init__(self, name, odata_type, event_id, event_count):
        self.name = name
        self.odata_type = odata_type
        self.event_id = event_id
        self.event_count = event_count

    def toJson(self):
        return json.dumps(self, default=lambda o: o.__dict__)