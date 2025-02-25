import time
import numpy as np
import sounddevice as sd
import whisper
import RPi.GPIO as GPIO
from datetime import datetime
import os

class STTProcessor:
    def __init__(self, 
                 button_pin=2, 
                 led_pin=3, 
                 sample_rate=16000, 
                 chunk_size=1024, 
                 model_size="tiny", 
                 transcripts_dir="/app/transcripts"):
        # Configuration
        self.BUTTON_PIN = button_pin
        self.LED_PIN = led_pin
        self.SAMPLE_RATE = sample_rate
        self.CHUNK_SIZE = chunk_size
        self.MODEL_SIZE = model_size
        self.TRANSCRIPTS_DIR = transcripts_dir

        # Setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.LED_PIN, GPIO.OUT)
        # Start with LED off (HIGH, since LED anode is at 3.3V)
        GPIO.output(self.LED_PIN, GPIO.HIGH)

        # Ensure transcripts directory exists
        os.makedirs(self.TRANSCRIPTS_DIR, exist_ok=True)

        # Load Whisper model
        print("Loading Whisper model...")
        self.model = whisper.load_model(self.MODEL_SIZE)
        print("Model loaded.")

    def record_audio_until_release(self):
        """
        Records audio from the microphone into an in-memory buffer
        until the button is released.
        """
        audio_buffer = []
        with sd.InputStream(samplerate=self.SAMPLE_RATE,
                            channels=1, dtype='float32') as stream:
            print("Recording... Press and hold the button. Release to stop.")
            # Keep recording while the button is pressed (GPIO input is LOW).
            while GPIO.input(self.BUTTON_PIN) == GPIO.LOW:
                data, _ = stream.read(self.CHUNK_SIZE)
                audio_buffer.append(data)
        return np.concatenate(audio_buffer, axis=0)

    def transcribe_audio(self, audio_data):
        """
        Transcribes the buffered audio using the Whisper model.
        Returns the transcription text.
        """
        print("Transcribing...")
        result = self.model.transcribe(audio_data, fp16=False)
        return result["text"]

    def cleanup(self):
        """
        Clean up the GPIO resources.
        """
        GPIO.cleanup()

    def run(self):
        """
        Main loop: waits for a button press to record audio, then transcribes it,
        and saves the transcript to a text file.
        """
        print("Waiting for button press to start recording...")
        try:
            while True:
                if GPIO.input(self.BUTTON_PIN) == GPIO.LOW:
                    # Turn LED on by setting pin LOW (inverted logic).
                    GPIO.output(self.LED_PIN, GPIO.LOW)

                    # Record
                    audio_data = self.record_audio_until_release()

                    # Turn LED off
                    GPIO.output(self.LED_PIN, GPIO.HIGH)

                    # Transcribe
                    transcription = self.transcribe_audio(audio_data)
                    print("Transcription:", transcription)

                    # Save transcript to file
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"transcript_{timestamp}.txt"
                    filepath = os.path.join(self.TRANSCRIPTS_DIR, filename)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(transcription)
                    print(f"Transcript saved to {filepath}")

                    time.sleep(0.5)  # Simple debounce
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Exiting...")
        finally:
            self.cleanup()
