#!/usr/bin/env python3
import gpiozero.pins.lgpio
import lgpio
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
from utils import STTProcessor

class ConversationalSTTProcessor(STTProcessor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We override the default topic to scribe/responses
        self.mqtt_topic = "scribe/responses"
        
        # Possibly re-init the MQTT or reuse parent's. 
        # Let's reuse parent's but set a different topic

    def run(self):
        """
        Instead of waiting for button, we do a loop that:
         - Waits for a "prompt to be played" event
         - Then automatically records, publishes to scribe/responses
        """
        print("[ConversationalSTT] Ready to record after each TTS prompt...")

        # In a simplified approach, you might do:
        while True:
            # 1) Wait for the user to press the green button to “start” a new chunk
            if self.green_button.is_pressed:
                self.led.on()
                audio_data = self.record_audio_until_red()
                self.led.off()

                print("[ConversationalSTT] Recording stopped. Transcribing...")
                transcript = self.transcribe_audio(audio_data)
                print("[ConversationalSTT] Transcript:", transcript)

                # We do NOT store a local file unless you want to
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename  = f"transcript_{timestamp}.txt"
                
                # Publish to scribe/responses
                if transcript:
                    self.publish_transcript(timestamp, filename, transcript)
                    
                time.sleep(1)
            time.sleep(0.1)
