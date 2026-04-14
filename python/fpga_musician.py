"""
fpga_musician.py - main demo for Project Update #1
Owen Richmond, EECE4632

Generates MIDI messages, synthesizes tones at 48kHz, applies effects,
saves WAV files and plots.

Usage: python fpga_musician.py
Deps:  pip install numpy matplotlib
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
from midi_utils    import make_sequence, pack_axi
from tone_generator import sequence_to_audio, save_wav, generate_tone, SAMPLE_RATE
from audio_effects  import tremolo, distortion, delay, fft_db

os.makedirs('output', exist_ok=True)

# note sequences used throughout
C_MAJOR = [('C4',0.4,80),('D4',0.4,80),('E4',0.4,80),('F4',0.4,80),
           ('G4',0.4,90),('A4',0.4,90),('B4',0.4,90),('C5',0.4,100)]

TWINKLE = [('C4',0.35,90),('C4',0.35,90),('G4',0.35,90),('G4',0.35,90),
           ('A4',0.35,95),('A4',0.35,95),('G4',0.70,85),
           ('F4',0.35,85),('F4',0.35,85),('E4',0.35,85),('E4',0.35,85),
           ('D4',0.35,80),('D4',0.35,80),('C4',0.70,100)]


# --- 1. MIDI messages ---
print("MIDI messages for C major scale:")
events = make_sequence(C_MAJOR)
with open('output/midi_messages.txt', 'w') as f:
    for ev in events:
        line = (f"t={ev['time_on']:.2f}s  {ev['note_name']:4s}  {ev['freq']:7.2f} Hz"
                f"  vel={ev['velocity']}  bytes={ev['midi_on'].hex(' ').upper()}"
                f"  axi=0x{pack_axi(ev['midi_on']):08X}")
        print(f"  {line}")
        f.write(line + '\n')


# --- 2. Synthesize audio ---
dry_scale   = sequence_to_audio(make_sequence(C_MAJOR))
dry_twinkle = sequence_to_audio(make_sequence(TWINKLE))
dry_a4      = generate_tone(440.0, 2.5, amplitude=0.85)  # single A4 for effect demos

save_wav('output/scale_dry.wav',   dry_scale)
save_wav('output/twinkle_dry.wav', dry_twinkle)


# --- 3. Apply effects ---
trem_out = tremolo(dry_a4, rate_hz=5.0, depth=0.8)
dist_out = distortion(dry_a4, gain=4.0, mode='soft')
dly_out  = delay(dry_a4, delay_ms=300, feedback=0.45, mix=0.5)

# full chain: distortion -> tremolo -> delay
def full_chain(audio):
    audio = distortion(audio, gain=2.5, mode='soft')
    audio = tremolo(audio, rate_hz=4.0, depth=0.6)
    audio = delay(audio, delay_ms=280, feedback=0.4, mix=0.4)
    return audio

save_wav('output/a4_tremolo.wav',        trem_out)
save_wav('output/a4_distortion.wav',     dist_out)
save_wav('output/a4_delay.wav',          dly_out)
save_wav('output/scale_full_chain.wav',  full_chain(dry_scale))
save_wav('output/twinkle_full_chain.wav',full_chain(dry_twinkle))


# --- 4. Plots ---

# waveform comparison
fig, axes = plt.subplots(4, 1, figsize=(13, 9), sharex=True)
t_ms = np.arange(len(dry_a4)) / SAMPLE_RATE * 1000
show = 4000

pairs = [
    (dry_a4,  'Dry (440 Hz)',                   'steelblue'),
    (trem_out,'Tremolo (5 Hz LFO, depth=0.8)',   'mediumseagreen'),
    (dist_out,'Distortion soft clip (gain=4x)',   'orangered'),
    (dly_out, 'Delay (300ms, fb=0.45, mix=0.5)', 'mediumpurple'),
]
for ax, (sig, title, color) in zip(axes, pairs):
    ax.plot(t_ms[:show], sig[:show], color=color, lw=0.8)
    ax.set_title(title, fontsize=10, loc='left')
    ax.set_ylabel('Amplitude', fontsize=8)
    ax.set_ylim(-1.15, 1.15)
    ax.grid(True, alpha=0.25)
axes[-1].set_xlabel('Time (ms)', fontsize=9)
plt.suptitle('FPGA Musician - Python Reference Effects\nOwen Richmond, EECE4632 Project Update #1', fontsize=11)
plt.tight_layout()
plt.savefig('output/effects_comparison.png', dpi=150)
plt.close()
print("  saved output/effects_comparison.png")

# FFT showing harmonic content from distortion, use chat for this because idc
dry_hard = distortion(dry_a4, gain=4.0, mode='hard')
fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
fft_cases = [
    (dry_a4,  'Dry',       'steelblue'),
    (dist_out,'Soft Clip', 'orangered'),
    (dry_hard,'Hard Clip', 'crimson'),
]
for ax, (sig, label, color) in zip(axes, fft_cases):
    f, db = fft_db(sig)
    ax.plot(f[f <= 6000], db[f <= 6000], color=color, lw=0.9)
    for h in range(1, 6):
        ax.axvline(440 * h, color='gray', ls='--', alpha=0.4, lw=0.7)
    ax.set_title(label, fontsize=10)
    ax.set_xlabel('Frequency (Hz)', fontsize=8)
    ax.set_ylim(-80, 5)
    ax.grid(True, alpha=0.25)
axes[0].set_ylabel('Magnitude (dB)', fontsize=8)
plt.suptitle('Distortion Harmonic Content - 440 Hz A4 (dashed = harmonics)', fontsize=11)
plt.tight_layout()
plt.savefig('output/distortion_fft.png', dpi=150)
plt.close()
print("  saved output/distortion_fft.png")

# signal at each stage of the chain
fig, axes = plt.subplots(2, 2, figsize=(13, 7), sharex=True)
after_d  = distortion(dry_a4, gain=2.5, mode='soft')
after_dt = tremolo(after_d, rate_hz=4.0, depth=0.6)
after_all= delay(after_dt, delay_ms=280, feedback=0.4, mix=0.4)
t2 = np.arange(3000) / SAMPLE_RATE * 1000
stage_data = [
    (dry_a4[:3000],   'Input',               'steelblue'),
    (after_d[:3000],  'After Distortion',    'orangered'),
    (after_dt[:3000], 'After Tremolo',       'mediumseagreen'),
    (after_all[:3000],'After Delay (Output)','goldenrod'),
]
for ax, (sig, title, color) in zip(axes.flatten(), stage_data):
    ax.plot(t2, sig, color=color, lw=0.8)
    ax.set_title(title, fontsize=10)
    ax.set_ylabel('Amplitude', fontsize=8)
    ax.set_xlabel('Time (ms)', fontsize=8)
    ax.set_ylim(-1.15, 1.15)
    ax.grid(True, alpha=0.25)
plt.suptitle('Signal at Each Stage of the Effects Chain', fontsize=11)
plt.tight_layout()
plt.savefig('output/pipeline_stages.png', dpi=150)
plt.close()
print("  saved output/pipeline_stages.png")

print("\nDone. Open output/*.wav in Audacity to listen.")
