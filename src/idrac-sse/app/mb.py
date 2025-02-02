import os
import stomp 
import logging
import json
import idrac_redfish as idrac
import utils
logger = logging.getLogger(__name__)
otel_receiver = os.environ.get('OTEL_RECEIVER')

class EventListener(stomp.ConnectionListener):
    def __init__(self, transport, timeout):
        self._transport = transport
        self._timeout = timeout

    def on_error(self, frame):
        logger.error('Stomp EventListener received error "%s"' % frame.body)

    def on_message(self, frame):
        logger.info("Stomp EventListener received message")
        logger.debug(frame.body)
        #listener_stats(frame.body)
        otlp_endpoint = f"{otel_receiver}/v1/logs"
        utils.send_to_endpoint(event=json.loads(frame.body), endpoint=otlp_endpoint, transport=self._transport, timeout=self._timeout)

class MetricListener(stomp.ConnectionListener):
    def __init__(self, transport, timeout):
        self._transport = transport
        self._timeout = timeout
    def on_error(self, frame):
        logger.error('Stomp MetricListener received error "%s"' % frame.body)

    def on_message(self, frame):
        logger.info("Stomp MetricListener received message")
        logger.debug(frame.body)
        otlp_endpoint = f"{otel_receiver}/v1/metrics"
        utils.send_to_endpoint(event=json.loads(frame.body), endpoint=otlp_endpoint, transport=self._transport, timeout=self._timeout)

class StompConnection:
    _instance = None

    def __new__(cls, host, port, user, password, transport, timeout):
        if cls._instance is None:
            cls._instance = super(StompConnection, cls).__new__(cls)
            cls._instance._initialize(host, port, user, password, transport, timeout)
            cls._instance._connect(transport=transport, timeout=timeout)
        return cls._instance

    def _initialize(self, host, port, user, password, transport, timeout):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.conn = None
        self.listener = None
        self.transport = transport
        self.timeout = timeout

    def _connect(self, transport, timeout):
        if self.conn is None:
            try:
                self.conn = stomp.Connection([(self.host, self.port)], "idrac-sse")
                event_listener = EventListener(transport=transport, timeout=timeout)
                metric_listener = MetricListener(transport=transport, timeout=timeout)
                self.conn.set_listener("event", event_listener)
                self.conn.set_listener("metric", metric_listener)
                self.conn.connect(self.user, self.password, wait=True)
                topic_event = "otel/event"
                topic_metric = "otel/metric"
                self.conn.subscribe(topic_event, "idrac-sse")
                self.conn.subscribe(topic_metric, "idrac-sse")
                logger.info(f"Connected to STOMP server {self.host}:{self.port}")
            except Exception as e:
                logger.error(f"Could not connect to activemq server {self.host}:{self.port}")
                logger.exception(e)

    def disconnect(self):
        if self.conn is not None:
            self.conn.disconnect()
            self.conn 

    def send(self, body, destination):
        try:
            logger.info(f"Sending message to STOMP server {self.host}:{self.port}, topic: {destination}")
            self.conn.send(body=body, destination=destination)
        except Exception as e:
            logger.error(f"Could not send message to activemq server {self.host}:{self.port}")
            logger.exception(e)