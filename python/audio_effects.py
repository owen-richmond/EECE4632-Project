"""
audio_effects.py - tremolo, distortion, delay reference implementations
Owen Richmond, EECE4632

These are the software versions that will be compared against the FPGA output.
All effects take int16 Q1.15 arrays (range [-32767, 32767]) at 48kHz.
this is like my gloden refrence, if the fpga can do this... ill be happy
"""

import numpy as np

SAMPLE_RATE = 48_000
Q15 = 32767  # Q1.15 fixed-point scale, matches HLS ap_fixed<16,1> on the FPGA


def tremolo(audio, rate_hz=5.0, depth=0.7):
    # LFO multiplies the amplitude, oscillates between (1-depth) and 1.0
    n = np.arange(len(audio))
    lfo  = 0.5 * (1.0 + np.sin(2.0 * np.pi * rate_hz * n / SAMPLE_RATE))
    gain = 1.0 - depth * (1.0 - lfo)
    return (audio.astype(np.int32) * gain).clip(-Q15, Q15).astype(np.int16)


def distortion(audio, gain=3.0, mode='soft'):
    driven = audio.astype(np.int32) * gain / Q15  # normalize for tanh/clip
    if mode == 'soft':
        # tanh gives a warm rounded clip, adds odd harmonics
        out = np.tanh(driven)
    elif mode == 'hard':
        # flat top, sounds buzzier, and adds more high harmonics see the graph. its ugly.
        out = np.clip(driven, -0.7, 0.7) / 0.7
    else:
        raise ValueError(f"unknown mode {mode}")
    peak = np.max(np.abs(out))
    if peak > 0:
        out = out / peak * 0.9
    return (out * Q15).clip(-Q15, Q15).astype(np.int16)


def delay(audio, delay_ms=300.0, feedback=0.4, mix=0.5):
    # circular buffer, models the BRAM delay line in the FPGA... hopefully
    delay_samples = int(delay_ms * SAMPLE_RATE / 1000)
    buf = np.zeros(delay_samples + len(audio), dtype=np.int32)
    out = np.zeros(len(audio), dtype=np.int32)
    for i in range(len(audio)):
        delayed = buf[i]
        out[i]  = int(audio[i] * (1 - mix) + delayed * mix)
        buf[i + delay_samples] = int(audio[i] + delayed * feedback)
    return out.clip(-Q15, Q15).astype(np.int16)

# FFT HELPER TO VISUALIZE DISTORTION HARMONICS, NOT PART OF FPGA CHAIN
def fft_db(audio):
    N   = len(audio)
    sig = audio.astype(np.float64) / Q15  # normalize back to [-1,1] for FFT
    mag = np.abs(np.fft.rfft(sig * np.hanning(N))) / N
    db  = 20 * np.log10(mag + 1e-10)
    f   = np.fft.rfftfreq(N, 1.0 / SAMPLE_RATE)
    return f, db

#basic test tones and plots thnak you CHATGPT !!!
if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from tone_generator import generate_tone, save_wav
    os.makedirs('output', exist_ok=True)

    dry = generate_tone(220.0, 2.0)

    save_wav('output/a4_tremolo.wav',    tremolo(dry, rate_hz=5.0, depth=0.8))
    save_wav('output/a4_distortion.wav', distortion(dry, gain=4.0, mode='soft'))
    save_wav('output/a4_delay.wav',      delay(dry, delay_ms=300, feedback=0.5, mix=0.5))
