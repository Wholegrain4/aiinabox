# stt_processor.py
from utils import STTProcessor
from gpiozero import Device
from gpiozero.pins.mock import MockFactory
Device.pin_factory = MockFactory()

def main():
    processor = STTProcessor()
    processor.run()

if __name__ == '__main__':
    main()
