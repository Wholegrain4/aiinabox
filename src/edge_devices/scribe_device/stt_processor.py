#!/usr/bin/env python3
import gpiozero.pins.lgpio
import lgpio  # ensures we're using LGPIO for hardware
from utils import STTProcessor

def main():
    processor = STTProcessor()
    processor.run()

if __name__ == '__main__':
    main()
