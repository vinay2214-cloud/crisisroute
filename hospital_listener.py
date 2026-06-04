import os
import json
import logging
from dotenv import load_dotenv
from google.cloud import pubsub_v1
from google.api_core.exceptions import AlreadyExists

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("hospital_listener")

def main():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or "crisisroute-2026-498212"
    topic_id = "hospital-alerts"
    subscription_id = "hospital-alerts-sub"
    
    # Auto-detect local emulator
    emulator_host = os.getenv("PUBSUB_EMULATOR_HOST")
    if emulator_host:
        logger.info(f"Emulator mode active. Target: {emulator_host}")
        
        # Setup publisher client to auto-create topic if missing in emulator
        pub_client = pubsub_v1.PublisherClient()
        topic_path = pub_client.topic_path(project_id, topic_id)
        try:
            pub_client.create_topic(name=topic_path)
            logger.info(f"Created emulator topic: {topic_path}")
        except AlreadyExists:
            pass
            
        # Setup subscriber client to auto-create subscription
        sub_client = pubsub_v1.SubscriberClient()
        sub_path = sub_client.subscription_path(project_id, subscription_id)
        try:
            sub_client.create_subscription(name=sub_path, topic=topic_path)
            logger.info(f"Created emulator subscription: {sub_path}")
        except AlreadyExists:
            pass
    else:
        logger.info("Production mode active. Using live GCP credentials.")

    sub_client = pubsub_v1.SubscriberClient()
    sub_path = sub_client.subscription_path(project_id, subscription_id)

    def callback(message):
        logger.info("Message received! Decoding payload...")
        try:
            payload = json.loads(message.data.decode("utf-8"))
            print(f"\n" + "═" * 40)
            print("🚨 NEW PATIENT ALERT DISPATCHED 🚨")
            print(f"CASE ID     : {payload.get('case_id')}")
            print(f"HOSPITAL ID : {payload.get('hospital_id')}")
            print(f"SEVERITY    : {payload.get('severity', '').upper()}")
            print(f"SPECIALTY   : {payload.get('specialty', '').upper()}")
            print(f"ETA         : {payload.get('eta_minutes')} minutes")
            print(f"TIMESTAMP   : {payload.get('timestamp')}")
            print("═" * 40 + "\n")
            message.ack()
            logger.info(f"Successfully acknowledged message {message.message_id}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Do not ack if failed so it can be redelivered
            message.nack()

    logger.info(f"Subscribing to subscription: {sub_path}")
    streaming_pull_future = sub_client.subscribe(sub_path, callback=callback)
    logger.info("Waiting for emergency alerts... (Press Ctrl+C to stop)")
    
    try:
        streaming_pull_future.result()
    except KeyboardInterrupt:
        logger.info("Stopping subscriber listener...")
        streaming_pull_future.cancel()
        streaming_pull_future.result()

if __name__ == "__main__":
    main()
