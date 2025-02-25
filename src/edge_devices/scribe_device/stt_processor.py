# stt_processor.py
from utils import STTProcessor
from gpiozero import Device
from gpiozero.pins.lgpio import LgpioFactory
Device.pin_factory = LgpioFactory()

def main():
    processor = STTProcessor()
    processor.run()

if __name__ == '__main__':
    main()
