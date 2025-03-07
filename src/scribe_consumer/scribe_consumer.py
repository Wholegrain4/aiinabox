import os
import json
import paho.mqtt.client as mqtt
import requests

MQTT_HOST = os.getenv("MQTT_BROKER_HOST", "192.168.40.187")
MQTT_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "mqttuser")
MQTT_PASS = os.getenv("MQTT_PASS", "password")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "scribe/transcripts")

# If you're calling your front_end service from inside the Docker Swarm:
# you'll typically use the *service name* (e.g. "front_end") as the hostname.
# For example:
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://front_end:5000/api/transcript")

def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with result code {rc}")
    client.subscribe(MQTT_TOPIC)
    print(f"Subscribed to topic: {MQTT_TOPIC}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        print(f"Received message: {payload}")

        # Example: forward this transcript to the Flask front_end’s new endpoint
        resp = requests.post(FRONTEND_URL, json=payload, timeout=5)
        print(f"POSTed transcript to front_end. Status code: {resp.status_code}")

    except Exception as e:
        print(f"Error handling message: {e}")

def main():
    client = mqtt.Client(client_id="scribe_consumer")
    client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to MQTT broker {MQTT_HOST}:{MQTT_PORT}...")
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()

if __name__ == "__main__":
    main()
