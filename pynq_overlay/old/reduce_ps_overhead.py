# reduce_ps_overhead.py -- Owen Richmond, EECE4632
# Measures three approaches to reducing Python/PS overhead per chunk.
#
# Baseline ~37us breaks down as:
#   FPGA compute  : 14.69us  (1469 cycles @ 100MHz)
#   flush+inval   : ~4us     (960 bytes each way through cache)
#   register_map  : ~18us    (6 param writes + AP_START via Python obj chain)
#   AP_DONE poll  : ~1us
#
# Approach 2 (static params): write params once, only AP_START each chunk.
# Approach 3 (direct MMIO):   bypass register_map entirely for AP_START/DONE.

from pynq import Overlay, allocate, MMIO
import numpy as np, time, os, sys

sys.path.insert(0, '/home/xilinx/jupyter_notebooks/Preliminary_Project')
from tone_generator import load_wav, SAMPLE_RATE

BASE        = '/home/xilinx/jupyter_notebooks/Preliminary_Project/'
NUM_SAMPLES = 480
TIMING_N    = 200
BUDGET_US   = NUM_SAMPLES / SAMPLE_RATE * 1e6   # 10,000 us

PARAMS = dict(
    dist_gain      = 3,
    trem_rate_step = int(5.0 * 65536 / SAMPLE_RATE),
    trem_depth_q15 = 20000,
    delay_n        = 4800,
    feedback_q15   = 13000,
    mix_q15        = 16000,
)

# ---- load audio ----
wav_path = BASE + 'test_tone.wav'
audio = (load_wav(wav_path) if os.path.exists(wav_path)
         else (np.sin(2*np.pi*440*np.arange(SAMPLE_RATE*3)/SAMPLE_RATE)*26000).astype(np.int16))
num_chunks = len(audio) // NUM_SAMPLES

# ---- load overlay (Build 1, same interface as Build 2) ----
print("Loading overlay...", end=' ', flush=True)
ol      = Overlay(BASE + 'chain.bit')
ip      = ol.chain_top_0
print("done")

# buffer addresses written once -- never change
in_buf  = allocate(shape=(NUM_SAMPLES,), dtype=np.int16)
out_buf = allocate(shape=(NUM_SAMPLES,), dtype=np.int16)
mem_ctrl = MMIO(0x80000000, 0x10000)
mem_ctrl.write(0x10,  in_buf.physical_address        & 0xFFFFFFFF)
mem_ctrl.write(0x14, (in_buf.physical_address >> 32) & 0xFFFFFFFF)
mem_ctrl.write(0x1C,  out_buf.physical_address        & 0xFFFFFFFF)
mem_ctrl.write(0x20, (out_buf.physical_address >> 32) & 0xFFFFFFFF)

# direct MMIO handle for AP_CTRL register (offset 0x00 in s_axi_CTRL bundle)
ctrl_addr = ol.ip_dict['chain_top_0']['phys_addr']
ap_mmio   = MMIO(ctrl_addr, 0x40)

def _chunk(i):
    return audio[(i % num_chunks) * NUM_SAMPLES : (i % num_chunks + 1) * NUM_SAMPLES].copy()

def measure(fn):
    times = []
    for i in range(TIMING_N):
        chunk = _chunk(i)
        t0 = time.perf_counter()
        fn(chunk)
        times.append((time.perf_counter() - t0) * 1e6)
    return float(np.median(times)), float(np.min(times))

# ── approach 1: baseline (params written every chunk) ────────────────────────
def run_baseline(chunk):
    in_buf[:] = chunk
    in_buf.flush()
    for k, v in PARAMS.items():
        setattr(ip.register_map, k, v)
    ip.register_map.CTRL.AP_START = 1
    while not ip.register_map.CTRL.AP_DONE:
        pass
    out_buf.invalidate()

# ── approach 2: params written once, AP_START via register_map ───────────────
for k, v in PARAMS.items():
    setattr(ip.register_map, k, v)

def run_static_params(chunk):
    in_buf[:] = chunk
    in_buf.flush()
    ip.register_map.CTRL.AP_START = 1
    while not ip.register_map.CTRL.AP_DONE:
        pass
    out_buf.invalidate()

# ── approach 3: params once + raw MMIO for AP_START/DONE ─────────────────────
# avoids Python attribute chain on every chunk's hot path
def run_direct_mmio(chunk):
    in_buf[:] = chunk
    in_buf.flush()
    ap_mmio.write(0x00, 0x1)              # AP_START
    while not (ap_mmio.read(0x00) & 0x2): # AP_DONE bit
        pass
    out_buf.invalidate()

# ── run ───────────────────────────────────────────────────────────────────────
print(f"Timing {TIMING_N} chunks per method...")
b_med, b_min = measure(run_baseline)
p_med, p_min = measure(run_static_params)
m_med, m_min = measure(run_direct_mmio)

print()
print("=" * 62)
print("  PS Overhead Reduction")
print("=" * 62)
print(f"  {'Method':<30} {'Median':>8}   {'Min':>8}   {'Saved':>8}")
print(f"  {'-'*30} {'-'*8}   {'-'*8}   {'-'*8}")
print(f"  {'Baseline (params every chunk)':<30} {b_med:>7.1f}µs  {b_min:>7.1f}µs  {'—':>8}")
print(f"  {'Static params (write once)':<30} {p_med:>7.1f}µs  {p_min:>7.1f}µs  {b_med-p_med:>+7.1f}µs")
print(f"  {'Direct MMIO (AP_START/DONE)':<30} {m_med:>7.1f}µs  {m_min:>7.1f}µs  {b_med-m_med:>+7.1f}µs")
print(f"  {'─'*62}")
print(f"  FPGA compute (HLS synthesis)               14.69µs")
print(f"  Budget (480 samples @ 48 kHz)         {BUDGET_US:>10,.0f}µs")
print("=" * 62)

in_buf.freebuffer()
out_buf.freebuffer()
