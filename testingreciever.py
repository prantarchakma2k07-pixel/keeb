import serial
from pynput.keyboard import Controller
import time

keyboard = Controller()
ser = serial.Serial('COM3', 115200, timeout=1)  # replace COM5

time.sleep(2)
print("Listening...")

while True:
    line = ser.readline().decode().strip()
    if not line:
        continue
    print("Got:", line)
    if line.startswith("KEY_"):
        key = line.replace("KEY_", "").lower()
        keyboard.press(key)
        keyboard.release(key)
