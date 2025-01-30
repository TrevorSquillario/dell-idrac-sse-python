# dell-idrac-sse-python

# Requirements
- Docker
- Python 3.x
- Dell iSM agent installed on host os

# Description
- This project is designed to open an SSE session with the iDRAC over the local 169.254.1.1 address provided by the iSM agent
- From there we can stream events and metrics to another endpoint
- OTLP support with OTEL OTLP Receiver connection