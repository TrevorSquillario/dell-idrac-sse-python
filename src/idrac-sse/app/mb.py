import os
import stomp 
import logging
import json
import idrac_redfish as idrac
import utils
logger = logging.getLogger(__name__)

otel_receiver = os.environ.get('iDRAC_SSE_OTEL_RECEIVER')
topic_event = os.environ.get('iDRAC_SSE_TOPIC_LOG')
topic_metric = os.environ.get('iDRAC_SSE_TOPIC_METRIC')
topic_stat = os.environ.get('iDRAC_SSE_TOPIC_STAT')

class LogListener(stomp.ConnectionListener):
    def __init__(self, transport, timeout):
        self._transport = transport
        self._timeout = timeout

    def on_error(self, frame):
        logger.error('Stomp LogListener received error "%s"' % frame.body)

    def on_message(self, frame):
        logger.info("Stomp LogListener received message")
        logger.debug(frame.body)
        otlp_endpoint = f"{otel_receiver}/v1/logs"
        event_json = json.loads(frame.body)
        #logger.info(f"DEBUG: {event_json}")
        utils.send_to_endpoint(event=event_json, endpoint=otlp_endpoint, transport=self._transport, timeout=self._timeout)

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
        event_json = json.loads(frame.body)
        utils.send_to_endpoint(event=event_json, endpoint=otlp_endpoint, transport=self._transport, timeout=self._timeout)

class StatListener(stomp.ConnectionListener):
    def __init__(self, transport, timeout):
        self._transport = transport
        self._timeout = timeout
    def on_error(self, frame):
        logger.error('Stomp StatListener received error "%s"' % frame.body)

    def on_message(self, frame):
        logger.info("Stomp StatListener received message")
        logger.debug(frame.body)
        otlp_endpoint = f"{otel_receiver}/v1/metrics"
        event_json = json.loads(frame.body)
        utils.send_to_endpoint(event=event_json, endpoint=otlp_endpoint, transport=self._transport, timeout=self._timeout)

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
                event_listener = LogListener(transport=transport, timeout=timeout)
                metric_listener = MetricListener(transport=transport, timeout=timeout)
                stat_listener = StatListener(transport=transport, timeout=timeout)
                self.conn.set_listener("log", event_listener)
                self.conn.set_listener("metric", metric_listener)
                self.conn.set_listener("stat", stat_listener)
                self.conn.connect(self.user, self.password, wait=True)
                self.conn.subscribe(topic_event, "idrac-sse-log")
                self.conn.subscribe(topic_metric, "idrac-sse-metric")
                self.conn.subscribe(topic_stat, "idrac-sse-stat")
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
            self.conn = None
            logger.error(f"Could not send message to activemq server {self.host}:{self.port}")
            logger.exception(e)