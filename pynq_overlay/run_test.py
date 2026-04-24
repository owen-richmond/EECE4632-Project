# run_test.py -- FPGA Musician minimal hardware test.
# Loads both overlays, verifies bit-exact vs the Python reference, measures latency.

from pynq import Overlay, allocate, MMIO
import numpy as np, time, os, sys

sys.path.insert(0, '/home/xilinx/jupyter_notebooks/Preliminary_Project')
from tone_generator import load_wav, SAMPLE_RATE
from audio_effects import chain_hls as python_ref

BASE      = '/home/xilinx/jupyter_notebooks/Preliminary_Project/'
N         = 480                            # samples/chunk = 10 ms at 48 kHz
TRIALS    = 300
BUDGET_US = N / SAMPLE_RATE * 1e6          # 10,000 us -- our real-time headroom

PARAMS = dict(
    dist_gain=3, trem_rate_step=int(5.0 * 65536 / SAMPLE_RATE), trem_depth_q15=20000,
    delay_n=4800, feedback_q15=13000, mix_q15=16000,
)

BUILDS = [
    # (name,            bitstream,    ip core,      synth II cycles)
    ('build1_pipeline', 'chain.bit',  'chain_top_0', 1470),
    ('build2_dataflow', 'chain2.bit', 'chain_top_2',  493),   # 3x faster on paper
]

# Source audio: WAV if the user dropped one in, else a sine so we have *something*.
wav = BASE + 'test_tone.wav'
if os.path.exists(wav):
    audio = load_wav(wav)
else:
    t = np.arange(SAMPLE_RATE * 3) / SAMPLE_RATE
    audio = (np.sin(2 * np.pi * 440 * t) * 26000).astype(np.int16)
num_chunks = len(audio) // N
get_chunk  = lambda i: audio[(i % num_chunks) * N : (i % num_chunks) * N + N].copy()

# Python golden reference for chunk 0 -- hardware output must match sample-for-sample.
ref0 = python_ref(get_chunk(0).astype(np.int32), **PARAMS)


def run_build(name, bit, ip_name, II_cyc):
    print(f"\n-- {name} " + "-" * (50 - len(name)))
    ol = Overlay(BASE + bit)
    ip = getattr(ol, ip_name)

    # Non-cacheable DMA buffers: skip flush/invalidate syscalls entirely.
    in_buf  = allocate(shape=(N,), dtype=np.int16, cacheable=False)
    out_buf = allocate(shape=(N,), dtype=np.int16, cacheable=False)

    # Point the IP's AXI master at our buffers (HLS-generated register offsets).
    mem = MMIO(0x80000000, 0x10000)
    for off, addr in [(0x10, in_buf.physical_address), (0x1C, out_buf.physical_address)]:
        mem.write(off,      addr        & 0xFFFFFFFF)
        mem.write(off + 4, (addr >> 32) & 0xFFFFFFFF)

    for k, v in PARAMS.items():
        setattr(ip.register_map, k, v)

    # Direct MMIO on AP_CTRL -- the register_map object is too polite for the hot path.
    ap = MMIO(ol.ip_dict[ip_name]['phys_addr'], 0x40)

    # bit-exact: one chunk, hardware vs python reference
    in_buf[:] = get_chunk(0)
    ap.write(0x00, 0x1)
    while not (ap.read(0x00) & 0x2): pass
    hw = np.array(out_buf, dtype=np.int32)
    print(f"  bit-exact vs ref : {'PASS' if np.array_equal(hw, ref0) else 'FAIL'}")

    # latency: fire, spin, repeat
    lat = np.empty(TRIALS)
    for i in range(TRIALS):
        in_buf[:] = get_chunk(i)
        t0 = time.perf_counter()
        ap.write(0x00, 0x1)
        while not (ap.read(0x00) & 0x2): pass
        lat[i] = (time.perf_counter() - t0) * 1e6

    med, mn = float(np.median(lat)), float(np.min(lat))
    II_us = II_cyc / 100.0     # 100 MHz fabric -> 1 cycle = 10 ns
    print(f"  latency median   : {med:6.2f} us  ({med/BUDGET_US*100:.3f}% of 10 ms budget)")
    print(f"  latency min      : {mn:6.2f} us")
    print(f"  FPGA II (synth)  : {II_us:6.2f} us  <- what Python can't reach")

    in_buf.freebuffer(); out_buf.freebuffer()
    return med, mn, II_us


# -- main ---------------------------------------------------------------
print(f"FPGA Musician -- {num_chunks} chunks of {N} samples @ {SAMPLE_RATE} Hz")
results = {}
for name, bit, ip_name, II in BUILDS:
    if not os.path.exists(BASE + bit):
        print(f"\n{name}: bit file missing, skipping.")
        continue
    results[name] = run_build(name, bit, ip_name, II)

# summary: the punchline from the report
if len(results) == 2:
    m1, _,   _   = results['build1_pipeline']
    m2, mn2, II2 = results['build2_dataflow']
    print("\n-- summary " + "-" * 49)
    print(f"  Wall-clock speedup (B1/B2) : {m1/m2:.2f}x")
    print(f"  FPGA II ceiling            : {1e6/II2:>10,.0f} chunks/sec")
    print(f"  Python actual (best case)  : {1e6/mn2:>10,.0f} chunks/sec")
    print(f"  -> DATAFLOW's throughput wins got eaten by PS overhead.")
    print(f"     The PL is waiting on the PS, not the other way around.")
