import paho.mqtt.client as mqtt
import base64, json, io
import sounddevice as sd
import soundfile as sf

class PromptListener:
    def __init__(self, broker, port, user, password, topic="scribe/prompts"):
        self.client = mqtt.Client(client_id="scribe_prompt_listener")
        self.client.username_pw_set(user, password)
        self.topic = topic
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(broker, port, keepalive=60)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, rc):
        print(f"Connected with rc={rc}; subscribing to {self.topic}")
        client.subscribe(self.topic)

    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            audio_b64 = data.get("audio", "")
            if audio_b64:
                audio_bytes = base64.b64decode(audio_b64)
                audio_file = io.BytesIO(audio_bytes)
                audio_data, fs = sf.read(audio_file)
                sd.play(audio_data, fs)
                sd.wait()
                print("Audio prompt played.")
        except Exception as e:
            print(f"Error in on_message: {e}")

if __name__ == "__main__":
    listener = PromptListener("192.168.40.187", 1883, "mqttuser", "password")
