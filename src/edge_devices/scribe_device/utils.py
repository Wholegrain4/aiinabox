import time
import numpy as np
import sounddevice as sd
import RPi.GPIO as GPIO
from datetime import datetime
import os
import subprocess
import tempfile
import wave

class STTProcessor:
    def __init__(self, 
                 button_pin=2, 
                 led_pin=3, 
                 sample_rate=16000, 
                 chunk_size=1024, 
                 model_size="tiny", 
                 transcripts_dir="/var/lib/aiinabox/transcripts"):
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

        # Initialize whisper.cpp paths
        # Adjust these paths as needed for your environment.
        print("Initializing whisper.cpp transcription engine...")
        self.whisper_binary = "./build/bin/whisper-cli"  # Path to the whisper.cpp binary
        self.model_file = "models/ggml-tiny.en.bin"        # Path to the ggml model file
        print("whisper.cpp transcription engine initialized.")

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
        Transcribes the buffered audio using the whisper.cpp binary.
        Returns the transcription text.
        """
        print("Transcribing audio using whisper.cpp...")

        # Convert float32 audio (range -1.0 to 1.0) to 16-bit PCM
        audio_int16 = (audio_data * 32767).astype(np.int16)

        # Write the audio data to a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_filename = tmp.name
            with wave.open(tmp_filename, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 2 bytes per sample for int16
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(audio_int16.tobytes())

        # Build command to call whisper.cpp
        # Example command:
        # ./build/bin/whisper-cli -m models/ggml-tiny.en.bin -f /path/to/temp.wav
        cmd = [self.whisper_binary, "-m", self.model_file, "-f", tmp_filename]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
            output = result.stdout
            # Depending on the binary's output format, you might need to parse it.
            # For simplicity, we assume the final line of stdout is the transcription.
            transcription = output.strip().split("\n")[-1]
        except subprocess.CalledProcessError as e:
            print("Error during transcription:", e.stderr)
            transcription = ""
        # Remove the temporary WAV file
        os.remove(tmp_filename)
        return transcription

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

                    # Record audio
                    audio_data = self.record_audio_until_release()

                    # Turn LED off
                    GPIO.output(self.LED_PIN, GPIO.HIGH)

                    # Transcribe the recorded audio
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
