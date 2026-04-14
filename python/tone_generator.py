"""
tone_generator.py - 48kHz sine wave synthesis from MIDI events
Owen Richmond, EECE4632
"""

import numpy as np
import wave
import os

SAMPLE_RATE = 48_000
Q15 = 32767  # Q1.15 fixed-point scale: maps [-1.0, 1.0] to [-32767, 32767]


def generate_tone(freq, duration, amplitude=0.85, attack_ms=5, release_ms=10):
    n = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, n, endpoint=False)
    samples = np.sin(2.0 * np.pi * freq * t)

    # simple attack/release to avoid clicks
    env = np.ones(n)
    atk = int(attack_ms * SAMPLE_RATE / 1000)
    rel = int(release_ms * SAMPLE_RATE / 1000)
    if atk > 0: env[:atk] = np.linspace(0, 1, atk)
    if rel > 0: env[-rel:] = np.linspace(1, 0, rel)

    return (samples * env * amplitude * Q15).astype(np.int16)


def sequence_to_audio(events):
    total = int(events[-1]['time_off'] * SAMPLE_RATE)
    audio = np.zeros(total, dtype=np.int32)
    for ev in events:
        amp  = (ev['velocity'] / 127.0) * 0.9
        tone = generate_tone(ev['freq'], ev['time_off'] - ev['time_on'], amp)
        start = int(ev['time_on'] * SAMPLE_RATE)
        end   = min(start + len(tone), total)
        audio[start:end] += tone[:end - start]
    peak = np.max(np.abs(audio))
    if peak > Q15:
        audio = (audio * Q15 // peak)
    return audio.clip(-Q15, Q15).astype(np.int16)


def save_wav(path, audio):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    pcm = np.clip(audio, -Q15, Q15).astype(np.int16)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    print(f"  saved {path}  ({len(pcm)/SAMPLE_RATE:.2f}s)")


if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from midi_utils import make_sequence
    scale = [('C4',0.4,80),('D4',0.4,80),('E4',0.4,80),('F4',0.4,80),
             ('G4',0.4,90),('A4',0.4,90),('B4',0.4,90),('C5',0.4,100)]
    audio = sequence_to_audio(make_sequence(scale))
    save_wav('output/scale_dry.wav', audio)
