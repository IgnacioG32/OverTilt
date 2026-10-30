import math
import struct
import wave
from pathlib import Path


RATE = 44100
OUTPUT = Path(__file__).resolve().parents[1] / "assets"


def write_tone(filename, notes):
    samples = []
    cursor = 0
    for frequency, duration, volume in notes:
        count = int(RATE * duration)
        for index in range(count):
            progress = index / count
            attack = min(1.0, progress / 0.025)
            release = min(1.0, (1.0 - progress) / 0.07)
            envelope = min(attack, release)
            sample = math.sin(2.0 * math.pi * frequency * (cursor + index) / RATE)
            samples.append(int(32767 * volume * envelope * sample))
        cursor += count
        # Small silence between notes keeps the short alerts distinct.
        samples.extend([0] * int(RATE * 0.035))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUTPUT / filename), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(RATE)
        audio.writeframes(b"".join(struct.pack("<h", value) for value in samples))


write_tone("defeat.wav", [(392, 0.16, 0.32), (294, 0.22, 0.32)])
write_tone("rest.wav", [(587, 0.14, 0.30), (740, 0.14, 0.30), (880, 0.24, 0.30)])
write_tone("detection_start.wav", [(660, 0.10, 0.24), (880, 0.14, 0.24)])
write_tone("detection_stop.wav", [(880, 0.10, 0.22), (660, 0.14, 0.22)])
