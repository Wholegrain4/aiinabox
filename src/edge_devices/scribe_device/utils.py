import os
import time
import json
import numpy as np
import sounddevice as sd
import subprocess
import tempfile
import wave
import scipy.signal
import paho.mqtt.client as mqtt

from gpiozero import Button, LED
from datetime import datetime

class STTProcessor:
    def __init__(self,
                 green_button_pin=2,
                 red_button_pin=3,
                 led_pin=17,
                 sample_rate=16000,
                 chunk_size=1024,
                 transcripts_dir="/app/transcripts"):
        """
        :param green_button_pin: BCM pin number for 'record' button (start).
        :param red_button_pin: BCM pin number for 'stop' button.
        :param led_pin: BCM pin number for an LED indicator.
        :param sample_rate: Desired audio sample rate for transcription.
        :param chunk_size: How many frames to read per audio capture loop.
        :param transcripts_dir: Directory path where transcripts are saved as .txt
        """

        # GPIO pins
        self.GREEN_BUTTON_PIN = green_button_pin
        self.RED_BUTTON_PIN   = red_button_pin
        self.LED_PIN          = led_pin

        # Audio settings
        self.SAMPLE_RATE = sample_rate
        self.CHUNK_SIZE  = chunk_size
        self.TRANSCRIPTS_DIR = transcripts_dir
        os.makedirs(self.TRANSCRIPTS_DIR, exist_ok=True)

        # Whisper paths
        self.whisper_binary = "./whisper.cpp/build/bin/whisper-cli"
        self.model_file     = "./whisper.cpp/models/ggml-tiny.en.bin"

        # Setup gpiozero
        print("Initializing gpiozero for GPIO (LGPIO backend).")
        self.green_button = Button(self.GREEN_BUTTON_PIN, pull_up=True)
        self.red_button   = Button(self.RED_BUTTON_PIN, pull_up=True)
        self.led          = LED(self.LED_PIN)
        self.led.off()

        # MQTT config (from env or default)
        self.mqtt_host  = os.getenv("MQTT_BROKER_HOST", "192.168.40.187")
        self.mqtt_port  = int(os.getenv("MQTT_BROKER_PORT", "1883"))
        self.mqtt_user  = os.getenv("MQTT_USER", "mqttuser")
        self.mqtt_pass  = os.getenv("MQTT_PASS", "password")
        self.mqtt_topic = os.getenv("MQTT_TOPIC", "scribe/transcripts")

        # Initialize MQTT client
        self.mqtt_client = mqtt.Client(client_id="scribe_pi")
        if self.mqtt_user and self.mqtt_pass:
            self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_pass)

        try:
            print(f"Connecting to MQTT broker {self.mqtt_host}:{self.mqtt_port} ...")
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
            self.mqtt_client.loop_start()
            print("MQTT connected, background loop started.")
        except Exception as e:
            print(f"MQTT connection error: {e}")

    def cleanup(self):
        """Close GPIO resources and stop MQTT loop."""
        self.green_button.close()
        self.red_button.close()
        self.led.close()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()

    def record_audio_until_red(self):
        """
        Records audio until the red button is pressed.
        Resamples if needed, then returns the raw audio samples.
        """
        default_input = sd.query_devices(kind='input')
        device_sample_rate = int(default_input['default_samplerate'])
        print("Using device sample rate:", device_sample_rate)

        audio_buffer = []
        with sd.InputStream(samplerate=device_sample_rate,
                            channels=1, dtype='float32') as stream:
            print("Recording... Press RED to stop.")
            while not self.red_button.is_pressed:
                data, _ = stream.read(self.CHUNK_SIZE)
                audio_buffer.append(data)

        audio_data = np.concatenate(audio_buffer, axis=0)

        # Resample if device sample rate differs from desired
        if device_sample_rate != self.SAMPLE_RATE:
            print(f"Resampling from {device_sample_rate} -> {self.SAMPLE_RATE}")
            n_samples = int(len(audio_data) * self.SAMPLE_RATE / device_sample_rate)
            audio_data = scipy.signal.resample(audio_data, n_samples)

        return audio_data

    def transcribe_audio(self, audio_data):
        """
        Runs whisper.cpp on audio_data and returns the transcript as a string.
        """
        print("Running whisper.cpp transcription...")
        audio_int16 = (audio_data * 32767).astype(np.int16)

        # Write to temp WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_name = tmp.name
            with wave.open(tmp_name, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(audio_int16.tobytes())

        # Build command
        cmd = [self.whisper_binary, "-m", self.model_file, "-f", tmp_name]
        transcription = ""
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    check=True, text=True)
            transcription = result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print("Whisper error:", e.stderr)
        finally:
            os.remove(tmp_name)

        return transcription

    def publish_transcript(self, timestamp, filename, transcript):
        """
        Publishes the transcript as a JSON message to the configured MQTT topic.
        """
        payload = {
            "timestamp": timestamp,
            "filename": filename,
            "transcript": transcript
        }
        try:
            self.mqtt_client.publish(self.mqtt_topic, json.dumps(payload), qos=1)
            print(f"Published transcript to MQTT topic '{self.mqtt_topic}'.")
        except Exception as e:
            print(f"Error publishing to MQTT: {e}")

    def run(self):
        """
        Main loop: Wait for green button -> record -> transcribe -> save file -> publish to MQTT
        """
        print("Waiting for GREEN button press to start recording...")
        try:
            while True:
                if self.green_button.is_pressed:
                    self.led.on()
                    audio_data = self.record_audio_until_red()
                    self.led.off()

                    print("Recording stopped. Transcribing...")
                    transcript = self.transcribe_audio(audio_data)
                    print("Transcript:", transcript)

                    # Save local file
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename  = f"transcript_{timestamp}.txt"
                    filepath  = os.path.join(self.TRANSCRIPTS_DIR, filename)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(transcript)
                    print(f"Transcript saved to {filepath}")

                    # Publish to MQTT
                    if transcript:
                        self.publish_transcript(timestamp, filename, transcript)

                    time.sleep(0.5)  # small delay
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Exiting (keyboard interrupt).")
        finally:
            self.cleanup()
