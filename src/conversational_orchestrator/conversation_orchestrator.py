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
SCRIBE_PROMPTS_TOPIC = "scribe/prompts"        
SCRIBE_RESPONSES_TOPIC = "scribe/responses"    
SCRIBE_FINAL_TOPIC = "scribe/transcripts"      

class ConversationOrchestrator:
    def __init__(self):
        print("[Orchestrator] Preloading Bark models (with smaller models if SUNO_USE_SMALL_MODELS=True)...")
        preload_models()

        self.mqtt_client = mqtt.Client(client_id="conversation_orchestrator")
        self.mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message

        # Hard-coded question list
        self.questions = [
            "Hello, I am the AI Scribe. Could you please tell me your name?",
            "What is your date of birth?",
            "Who brought you into the office today?",
            "What is your gender and how old are you?",
            "Have you been seen in this office before, in the ER or by another doctor in the last three months?",
            "If yes, what were you seen for?",
            "Could you describe the symptoms you're experiencing?",
            "How long have you been ill?",
            "Have you had a fever in the last few days?",
            "Have you been vommitting?",
            "Have you had diarrhea?",
            "Have you had any eye discharge?",
            "Have you had any nasal congestion?",
            "Have you had any nasal drainage?",
            "Have you had a sore throat?",
            "Have you had a headache?",
            "Have you had any ear pain?",
            "Have you had any abdominal pain?",
            "Have you had a rash?",
            "Have you had a cough?",
            "Have you had any trouble breathing?",
            "Have you had any trouble eating?",
            "Have you been active?",
            "Are there any others sick at the house?",
            "Are there smokers at the home?",
            "Are all your vaccines up to date?",
            "Are you on any medications?",
            "Do you have any allergies?",
            "All right. Is there anything else you'd like the doctor to know?",
        ]
        self.current_question_idx = 0
        self.conversation_buffer = []
        self.active_conversation = False

        # 1) Pre-generate the audio for each question once, store base64 WAV in a dictionary
        self.question_audio_cache = {}
        print("[Orchestrator] Pre-generating audio for all questions. This may take a moment...")
        for q in self.questions:
            audio_b64 = self._generate_audio_b64(q)
            self.question_audio_cache[q] = audio_b64
        print("[Orchestrator] All questions pre-generated. Ready.")

    def _generate_audio_b64(self, text):
        """
        Generates audio from text using Bark, writes to an in-memory buffer,
        then returns base64-encoded WAV. 
        """
        try:
            audio_array = generate_audio(text)
            output_buffer = io.BytesIO()
            wavfile.write(output_buffer, SAMPLE_RATE, audio_array)
            output_buffer.seek(0)
            wav_data = output_buffer.read()
            audio_b64 = base64.b64encode(wav_data).decode("utf-8")
            return audio_b64
        except Exception as e:
            print(f"[Orchestrator] Error generating audio for '{text}': {e}")
            return None

    def on_connect(self, client, userdata, flags, rc):
        print(f"[Orchestrator] Connected to MQTT broker with rc={rc}")
        client.subscribe(SCRIBE_RESPONSES_TOPIC)
        print(f"[Orchestrator] Subscribed to topic: {SCRIBE_RESPONSES_TOPIC}")

    def on_message(self, client, userdata, msg):
        payload = json.loads(msg.payload.decode("utf-8"))
        transcript_chunk = payload.get("transcript", "")
        print(f"[Orchestrator] Received partial transcript: {transcript_chunk}")

        self.conversation_buffer.append(transcript_chunk)

        if self.current_question_idx < len(self.questions):
            self.ask_next_question()
        else:
            self.finalize_conversation()

    def ask_next_question(self):
        if self.current_question_idx >= len(self.questions):
            self.finalize_conversation()
            return

        question = self.questions[self.current_question_idx]
        self.current_question_idx += 1

        print(f"[Orchestrator] Sending question #{self.current_question_idx}: {question}")
        # 2) Instead of calling Bark now, we use our pre-generated audio from the dictionary
        audio_b64 = self.question_audio_cache.get(question)
        if not audio_b64:
            print("[Orchestrator] No pre-generated audio found. (Skipping question.)")
            return

        prompt_payload = {
            "audio": audio_b64,
            "prompt_text": question
        }
        self.mqtt_client.publish(SCRIBE_PROMPTS_TOPIC, json.dumps(prompt_payload), qos=1)
        print("[Orchestrator] Prompt published.")

    def start_conversation(self):
        self.active_conversation = True
        self.current_question_idx = 0
        self.conversation_buffer = []
        print("[Orchestrator] Starting conversation!")
        self.ask_next_question()

    def finalize_conversation(self):
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
        time.sleep(2)  
        self.start_conversation()
        while True:
            time.sleep(1)


if __name__ == "__main__":
    orch = ConversationOrchestrator()
    orch.run()
