from kafka import KafkaConsumer, KafkaProducer


producer = KafkaProducer(
    bootstrap_servers=["kafka:9092"]
)

def send(msg):
    producer.send("otel", value="Hello, World!".encode("utf-8"))

# Create a KafkaConsumer instance
consumer = KafkaConsumer(
    bootstrap_servers=['kafka:9092'], 
    auto_offset_reset='earliest', 
    enable_auto_commit=False
)

# Subscribe to a specific topic
consumer.subscribe(topics=['otel'])

# Poll for new messages
while True:
    msg = consumer.poll(timeout_ms=1000)
    if msg:
        for topic, partition, offset, key, value in msg.items():
            print("Topic: {} | Partition: {} | Offset: {} | Key: {} | Value: {}".format(
                topic, partition, offset, key, value.decode("utf-8")
            ))
    else:
        print("No new messages")


