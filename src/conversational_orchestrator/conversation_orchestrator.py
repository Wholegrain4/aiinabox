#!/usr/bin/env python3
import os
import json
import base64
import paho.mqtt.client as mqtt
import time
import io
import scipy.io.wavfile as wavfile

# Import Bark functions
from bark import SAMPLE_RATE, generate_audio, preload_models

MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "192.168.40.187")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USER        = os.getenv("MQTT_USER", "mqttuser")
MQTT_PASS        = os.getenv("MQTT_PASS", "ballerselite40")

# MQTT Topics
SCRIBE_PROMPTS_TOPIC = "scribe/prompts"        # Orchestrator -> Pi
SCRIBE_RESPONSES_TOPIC = "scribe/responses"      # Pi -> Orchestrator
SCRIBE_FINAL_TOPIC = "scribe/transcripts"        # Final transcript

class ConversationOrchestrator:
    def __init__(self):
        # Preload Bark models once at startup
        print("[Orchestrator] Preloading Bark models...")
        preload_models()

        self.mqtt_client = mqtt.Client(client_id="conversation_orchestrator")
        self.mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message

        # Hard-coded question list (can be dynamic)
        self.questions = [
            "Hello, I am the AI Scribe. Could you please tell me your name?",
            "Thank you. Could you describe the symptoms you're experiencing?",
            "Got it. Have you had a fever in the last few days?",
            "All right. Is there anything else you'd like the doctor to know?"
        ]
        self.current_question_idx = 0
        self.conversation_buffer = []

        # Flag to track if we are in an active conversation
        self.active_conversation = False

    def on_connect(self, client, userdata, flags, rc):
        print(f"[Orchestrator] Connected to MQTT broker with rc={rc}")
        # Subscribe to responses from the scribe device
        client.subscribe(SCRIBE_RESPONSES_TOPIC)
        print(f"[Orchestrator] Subscribed to topic: {SCRIBE_RESPONSES_TOPIC}")

    def on_message(self, client, userdata, msg):
        # Receive partial transcripts from the scribe device
        payload = json.loads(msg.payload.decode("utf-8"))
        transcript_chunk = payload.get("transcript", "")
        print(f"[Orchestrator] Received partial transcript: {transcript_chunk}")

        # Append chunk to conversation buffer
        self.conversation_buffer.append(transcript_chunk)

        # Decide if more questions remain or if we finalize
        if self.current_question_idx < len(self.questions):
            self.ask_next_question()
        else:
            self.finalize_conversation()

    def ask_next_question(self):
        # If no more questions remain, finalize
        if self.current_question_idx >= len(self.questions):
            self.finalize_conversation()
            return

        question = self.questions[self.current_question_idx]
        self.current_question_idx += 1

        print(f"[Orchestrator] Sending question #{self.current_question_idx}: {question}")
        audio_b64 = self.synthesize_with_suno_bark(question)
        if not audio_b64:
            print("[Orchestrator] Error synthesizing audio, skipping question.")
            return

        # Publish TTS prompt to the scribe device via MQTT
        prompt_payload = {
            "audio": audio_b64,
            "prompt_text": question
        }
        self.mqtt_client.publish(SCRIBE_PROMPTS_TOPIC, json.dumps(prompt_payload), qos=1)
        print("[Orchestrator] Prompt published.")

    def synthesize_with_suno_bark(self, text):
        """
        Uses the Bark model via its Python API to generate audio from the provided text.
        The generated audio is then converted to WAV bytes in memory and base64-encoded.
        """
        output_buffer = io.BytesIO()
        try:
            # Generate audio as a numpy array using Bark
            audio_array = generate_audio(text)
            # Write the numpy array as a WAV file into a memory buffer
            wavfile.write(output_buffer, SAMPLE_RATE, audio_array)
            output_buffer.seek(0)
            wav_data = output_buffer.read()
            audio_b64 = base64.b64encode(wav_data).decode("utf-8")
            print("[Orchestrator] Audio synthesis successful.")
            return audio_b64
        except Exception as e:
            print(f"[Orchestrator] Error in Bark synthesis: {e}")
            return None

    def start_conversation(self):
        """
        Starts a new conversation session.
        """
        self.active_conversation = True
        self.current_question_idx = 0
        self.conversation_buffer = []
        print("[Orchestrator] Starting conversation!")
        self.ask_next_question()

    def finalize_conversation(self):
        """
        Finalizes the conversation by merging all transcripts and publishing the final transcript.
        """
        print("[Orchestrator] Finalizing conversation...")
        final_transcript = "\n".join(self.conversation_buffer)
        timestamp = int(time.time())
        filename = f"conversation_{timestamp}.txt"

        payload = {
            "timestamp": timestamp,
            "filename": filename,
            "transcript": final_transcript
        }
        self.mqtt_client.publish(SCRIBE_FINAL_TOPIC, json.dumps(payload), qos=1)
        print("[Orchestrator] Final transcript published.")
        self.active_conversation = False
        self.current_question_idx = 0
        self.conversation_buffer = []

    def run(self):
        print("[Orchestrator] Connecting to MQTT broker...")
        self.mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
        self.mqtt_client.loop_start()
        time.sleep(2)  # Brief pause before starting
        self.start_conversation()
        while True:
            time.sleep(1)

if __name__ == "__main__":
    orch = ConversationOrchestrator()
    orch.run()
