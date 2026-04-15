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

# ---- HLS-matching reference functions (used by pynq_test*.py on the board) ----
# these replicate the exact fixed-point integer arithmetic from the C++ so you
# can compare the FPGA output sample-for-sample and get a perfect match
# distortion_hls skips the peak normalization that distortion() does, since
# the FPGA cant do that without buffering the whole chunk and scanning it twice

_SIN_LUT64 = [
        0,  3211,  6392,  9511, 12539, 15446, 18204, 20787,
    23169, 25329, 27244, 28897, 30272, 31356, 32137, 32609,
    32767, 32609, 32137, 31356, 30272, 28897, 27244, 25329,
    23169, 20787, 18204, 15446, 12539,  9511,  6392,  3211,
        0, -3211, -6392, -9511,-12539,-15446,-18204,-20787,
   -23169,-25329,-27244,-28897,-30272,-31356,-32137,-32609,
   -32767,-32609,-32137,-31356,-30272,-28897,-27244,-25329,
   -23169,-20787,-18204,-15446,-12539, -9511, -6392, -3211
]
_Q15_MAX = 32767
_Q15_MIN = -32768


def distortion_hls(audio, gain=1):
    # hard clip only, no normalization -- matches distortion_top HLS bit-exactly
    driven = audio.astype(np.int32) * np.int32(gain)
    return driven.clip(_Q15_MIN, _Q15_MAX).astype(np.int16)


# module-level state mirrors the C++ static variables so the LFO phase and
# delay buffer stay continuous across 10ms chunks, same as they do on hardware
_chain_phase = 0
_chain_delay_buf = [0] * 12000
_chain_wp = 0


def chain_hls(audio, dist_gain=1, trem_rate_step=0, trem_depth_q15=0,
              delay_n=1, feedback_q15=0, mix_q15=0):
    # integer-exact replica of chain_top C++ (build1 & build2 give same result)
    global _chain_phase, _chain_delay_buf, _chain_wp
    MAX_DELAY_SAMP = 12000
    N = len(audio)
    mid1 = [0] * N
    mid2 = [0] * N
    out  = np.zeros(N, dtype=np.int16)

    # stage 1: distortion
    for i in range(N):
        d = int(audio[i]) * dist_gain
        mid1[i] = max(_Q15_MIN, min(_Q15_MAX, d))

    # stage 2: tremolo
    for i in range(N):
        lfo_01 = (_SIN_LUT64[(_chain_phase >> 10) & 0x3F] + _Q15_MAX) >> 1
        gq = (_Q15_MAX - trem_depth_q15) + ((trem_depth_q15 * lfo_01) >> 15)
        s  = (mid1[i] * gq) >> 15
        mid2[i] = max(_Q15_MIN, min(_Q15_MAX, s))
        _chain_phase = (_chain_phase + trem_rate_step) & 0xFFFF

    # stage 3: delay
    dn = max(1, min(delay_n, MAX_DELAY_SAMP - 1))
    for i in range(N):
        rp = _chain_wp - dn
        if rp < 0:
            rp += MAX_DELAY_SAMP
        delayed = _chain_delay_buf[rp]
        dry = (mid2[i] * (_Q15_MAX - mix_q15)) >> 15
        wet = (delayed  *             mix_q15)  >> 15
        s   = dry + wet
        out[i] = max(_Q15_MIN, min(_Q15_MAX, s))
        fb = mid2[i] + ((delayed * feedback_q15) >> 15)
        _chain_delay_buf[_chain_wp] = max(_Q15_MIN, min(_Q15_MAX, fb))
        _chain_wp = (_chain_wp + 1) % MAX_DELAY_SAMP

    return out


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
