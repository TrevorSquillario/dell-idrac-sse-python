import docker
import argparse

parser = argparse.ArgumentParser(description='Spin up multiple instances of a container for testing')
parser.add_argument('-c','--count', help='Container Count', required=False, default=10)
parser.add_argument('-s','--start', help='Start', required=False, action='store_true')
parser.add_argument('-k','--kill', help='Kill', required=False, action='store_true')
args = parser.parse_args()

client = docker.from_env()

if args.start:
    # ghcr.io/trevorsquillario/idrac-sse:latest

    for i in range(args.count):
        client.containers.run("dell-idrac-sse-python-idrac-sse-testserver", 
                            name=f"idrac-sse-testserver-{i}",
                            network="dell-idrac-sse-python_idrac-sse-demo",
                            detach=True)
        
    print(client.containers.list())

if args.kill:
    containers = client.containers.list()
    for c in containers:
        c.remove(force=True)
