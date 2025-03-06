# stt_processor.py
import gpiozero.pins.lgpio
import lgpio

# Monkey patch to force LGPIOFactory to use gpiochip0 explicitly
def __patched_init(self, chip=None):
    gpiozero.pins.lgpio.LGPIOFactory.__bases__[0].__init__(self)
    chip = 0  # Raspberry Pi 5 uses gpiochip0
    self._handle = lgpio.gpiochip_open(chip)
    self._chip = chip
    self.pin_class = gpiozero.pins.lgpio.LGPIOPin

gpiozero.pins.lgpio.LGPIOFactory.__init__ = __patched_init

from utils import STTProcessor


def main():
    processor = STTProcessor()
    processor.run()


if __name__ == '__main__':
    main()
