import time
import numpy as np
import sounddevice as sd
from gpiozero import LED, Button
from datetime import datetime
import os
import subprocess
import tempfile
import wave
import scipy.signal  # For resampling

class STTProcessor:
    def __init__(self, 
                 button_pin=2, 
                 led_pin=3, 
                 sample_rate=16000,  # Desired sample rate for Whisper
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

        # Setup gpiozero objects for the button and LED.
        print("Initializing gpiozero for GPIO access...")
        self.button = Button(self.BUTTON_PIN, pull_up=True)
        self.led = LED(self.LED_PIN)
        self.led.off()

        # Ensure transcripts directory exists
        os.makedirs(self.TRANSCRIPTS_DIR, exist_ok=True)

        # Initialize whisper.cpp paths
        print("Initializing whisper.cpp transcription engine...")
        # Updated path to point to the correct location
        self.whisper_binary = "./whisper.cpp/build/bin/whisper-cli"  # Corrected path
        self.model_file = "models/ggml-tiny.en.bin"        # Path to the ggml model file
        print("whisper.cpp transcription engine initialized.")

    def record_audio_until_release(self):
        """
        Records audio from the microphone into an in-memory buffer
        until the button is released.
        It uses the device's default sample rate and resamples to the desired rate if needed.
        """
        # Query default input device sample rate
        default_input = sd.query_devices(kind='input')
        device_sample_rate = int(default_input['default_samplerate'])
        print("Using device sample rate:", device_sample_rate)

        audio_buffer = []
        with sd.InputStream(samplerate=device_sample_rate,
                            channels=1, dtype='float32') as stream:
            print("Recording... Press and hold the button. Release to stop.")
            while self.button.is_pressed:
                data, _ = stream.read(self.CHUNK_SIZE)
                audio_buffer.append(data)
        audio_data = np.concatenate(audio_buffer, axis=0)

        # Resample to the desired sample rate if necessary
        if device_sample_rate != self.SAMPLE_RATE:
            print(f"Resampling audio from {device_sample_rate} Hz to {self.SAMPLE_RATE} Hz.")
            num_samples = int(len(audio_data) * self.SAMPLE_RATE / device_sample_rate)
            audio_data = scipy.signal.resample(audio_data, num_samples)
        return audio_data

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
        cmd = [self.whisper_binary, "-m", self.model_file, "-f", tmp_filename]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
            output = result.stdout
            # For simplicity, assume the final line is the transcription.
            transcription = output.strip().split("\n")[-1]
        except subprocess.CalledProcessError as e:
            print("Error during transcription:", e.stderr)
            transcription = ""
        # Remove the temporary WAV file
        os.remove(tmp_filename)
        return transcription

    def cleanup(self):
        """
        Clean up the gpiozero resources.
        """
        self.button.close()
        self.led.close()

    def run(self):
        """
        Main loop: waits for a button press to record audio, transcribes it,
        and saves the transcript to a text file.
        """
        print("Waiting for button press to start recording...")
        try:
            while True:
                if self.button.is_pressed:
                    self.led.on()
                    audio_data = self.record_audio_until_release()
                    self.led.off()
                    transcription = self.transcribe_audio(audio_data)
                    print("Transcription:", transcription)
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

def main():
    processor = STTProcessor()
    processor.run()

if __name__ == '__main__':
    main()
