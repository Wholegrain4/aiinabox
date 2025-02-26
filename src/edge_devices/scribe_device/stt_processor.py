# stt_processor.py
from utils import STTProcessor
from gpiozero import Device

def main():
    processor = STTProcessor()
    processor.run()

if __name__ == '__main__':
    main()
