import os
import time
import numpy as np
import sounddevice as sd
import subprocess
import tempfile
import wave
import scipy.signal

from gpiozero import Device, LED, Button
from datetime import datetime


class STTProcessor:
    def __init__(self,
                 green_button_pin=2,
                 red_button_pin=3,
                 led_pin=17,
                 sample_rate=16000,
                 chunk_size=1024,
                 model_size="tiny",
                 transcripts_dir="/app/transcripts"):

        # Configuration
        self.GREEN_BUTTON_PIN = green_button_pin
        self.RED_BUTTON_PIN = red_button_pin
        self.LED_PIN = led_pin
        self.SAMPLE_RATE = sample_rate
        self.CHUNK_SIZE = chunk_size
        self.MODEL_SIZE = model_size
        self.TRANSCRIPTS_DIR = transcripts_dir

        # Setup gpiozero objects for the green and red buttons and the LED.
        print("Initializing gpiozero for GPIO access using LGPIO backend...")
        self.green_button = Button(self.GREEN_BUTTON_PIN, pull_up=True)
        self.red_button = Button(self.RED_BUTTON_PIN, pull_up=True)
        self.led = LED(self.LED_PIN)
        self.led.off()

        # Ensure transcripts directory exists
        os.makedirs(self.TRANSCRIPTS_DIR, exist_ok=True)

        # Initialize whisper.cpp paths
        print("Initializing whisper.cpp transcription engine...")
        self.whisper_binary = "./whisper.cpp/build/bin/whisper-cli"  # Path to the binary
        self.model_file = "./whisper.cpp/models/ggml-tiny.en.bin"    # Path to the model file
        print("whisper.cpp transcription engine initialized.")

    def record_audio_until_red(self):
        """
        Starts recording audio using the device's default sample rate and
        continues recording until the red button is pressed.
        If the device sample rate differs from the desired rate, the audio is resampled.
        """
        # Query default input device sample rate
        default_input = sd.query_devices(kind='input')
        device_sample_rate = int(default_input['default_samplerate'])
        print("Using device sample rate:", device_sample_rate)

        audio_buffer = []
        with sd.InputStream(samplerate=device_sample_rate,
                            channels=1, dtype='float32') as stream:
            print("Recording started. Speak now. Press the RED button to stop recording.")
            # Record continuously until the red button is pressed.
            while not self.red_button.is_pressed:
                data, _ = stream.read(self.CHUNK_SIZE)
                audio_buffer.append(data)

        audio_data = np.concatenate(audio_buffer, axis=0)

        # Resample if necessary
        if device_sample_rate != self.SAMPLE_RATE:
            print(f"Resampling audio from {device_sample_rate} Hz to {self.SAMPLE_RATE} Hz.")
            num_samples = int(len(audio_data) * self.SAMPLE_RATE / device_sample_rate)
            audio_data = scipy.signal.resample(audio_data, num_samples)

        return audio_data

    def transcribe_audio(self, audio_data):
        """
        Transcribes the buffered audio using the whisper.cpp binary.
        Returns the full transcription text.
        """
        print("Transcribing audio using whisper.cpp...")

        # Convert float32 audio (range -1.0 to 1.0) to 16-bit PCM
        audio_int16 = (audio_data * 32767).astype(np.int16)

        # Write audio to a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_filename = tmp.name
            with wave.open(tmp_filename, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(audio_int16.tobytes())

        # Build the command to call the whisper.cpp binary
        cmd = [self.whisper_binary, "-m", self.model_file, "-f", tmp_filename]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    check=True, text=True)
            output = result.stdout
            # Use the entire output as the transcription.
            transcription = output.strip()
        except subprocess.CalledProcessError as e:
            print("Error during transcription:", e.stderr)
            transcription = ""

        os.remove(tmp_filename)
        return transcription

    def cleanup(self):
        """
        Closes gpiozero resources.
        """
        self.green_button.close()
        self.red_button.close()
        self.led.close()

    def run(self):
        """
        Main loop: waits for the green button to be pressed to start recording.
        Once the green button is pressed, the LED is turned on and recording starts.
        Recording continues (even after green is released) until the red button is pressed.
        Then, transcription is performed and saved to a transcript file.
        """
        print("Waiting for GREEN button press to start recording...")
        try:
            while True:
                if self.green_button.is_pressed:
                    print("Green button pressed. Starting recording...")
                    self.led.on()  # Turn LED on when recording starts

                    # Record audio until the red button is pressed.
                    audio_data = self.record_audio_until_red()

                    self.led.off()  # Turn LED off after recording stops
                    print("Recording stopped. Processing transcription...")

                    transcription = self.transcribe_audio(audio_data)
                    print("Transcription:", transcription)

                    # Save the transcription to a file.
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"transcript_{timestamp}.txt"
                    filepath = os.path.join(self.TRANSCRIPTS_DIR, filename)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(transcription)
                    print(f"Transcript saved to {filepath}")

                    # Small delay before next cycle.
                    time.sleep(0.5)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Exiting...")
        finally:
            self.cleanup()

def main():
    processor = STTProcessor()
    processor.run()

if __name__ == '__main__':
    main()
