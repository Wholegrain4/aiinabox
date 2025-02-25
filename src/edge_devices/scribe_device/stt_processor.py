# stt_processor.py
from utils import STTProcessor
from gpiozero import Device
from gpiozero.pins.lgpio import LGPIOFactory
Device.pin_factory = LGPIOFactory()

def main():
    processor = STTProcessor()
    processor.run()

if __name__ == '__main__':
    main()
