import stomp 
import os
import logging
import json
import idrac_redfish as idrac


otel_receiver = os.environ.get('OTEL_RECEIVER')

logger = logging.getLogger('idrac-sse')

class EventListener(stomp.ConnectionListener):
    def on_error(self, frame):
        logger.error('Stomp EventListener received error "%s"' % frame.body)

    def on_message(self, frame):
        logger.info("Stomp EventListener received message")
        logger.debug(frame.body)
        otlp_endpoint = f"{otel_receiver}/v1/logs"
        idrac.send_to_endpoint(event=json.loads(frame.body), endpoint=otlp_endpoint)

class MetricListener(stomp.ConnectionListener):
    def on_error(self, frame):
        logger.error('Stomp MetricListener received error "%s"' % frame.body)

    def on_message(self, frame):
        logger.info("Stomp MetricListener received message")
        logger.debug(frame.body)
        otlp_endpoint = f"{otel_receiver}/v1/metrics"
        idrac.send_to_endpoint(event=json.loads(frame.body), endpoint=otlp_endpoint)