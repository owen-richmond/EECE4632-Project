# pynq_test_chain.py -- Owen Richmond, EECE4632
# tests Build 1 (chain.bit) and/or Build 2 (chain2.bit) on the AUP-ZU3.
# auto-detects which builds are present and runs both if available.
# tests: bit-exact match vs python reference, state continuity across chunks,
# and measured hardware latency. prints a side-by-side comparison if both run.

# ---- cell 0: round-trip timing estimate (no hardware needed) ----
#
# Two separate AXI buses are in play:
#   s_axilite (via GP0, 32-bit):  control only -- params, AP_START, AP_DONE
#   m_axi_MEM (via HP0, 128-bit): audio data -- DMA burst read/write to DDR
#
# They are independent. The data path (HP0 burst) handles 960 bytes in ~2-4 us.
# Python-side overhead (flush, copy, axilite writes) dominates over the hardware.

SAMPLE_RATE = 48_000
NUM_SAMPLES = 480
BUDGET_US   = (NUM_SAMPLES / SAMPLE_RATE) * 1e6   # 10,000 us

CLOCK_MHZ        = 100.0
FPGA_CYCLES_B1   = 1469
fpga_compute_us  = FPGA_CYCLES_B1 / CLOCK_MHZ     # 14.69 us
HP0_MB_S         = 500
dma_bytes        = NUM_SAMPLES * 2 * 2             # read + write, 960 bytes each
dma_us           = (dma_bytes / (HP0_MB_S * 1e6)) * 1e6
axilite_us       = 2.0 * (1 + 1)                  # AP_START + AP_DONE poll
python_misc_us   = 5.0                             # flush + copy
roundtrip_us     = fpga_compute_us + dma_us + axilite_us + python_misc_us

print("=" * 60)
print(f"  Timing estimate -- chain_top @ {CLOCK_MHZ:.0f} MHz, {NUM_SAMPLES} samples")
print("=" * 60)
print(f"  Budget                : {BUDGET_US:,.0f} us  (1 chunk at 48 kHz)")
print(f"  FPGA compute (B1)     : {fpga_compute_us:.2f} us  ({FPGA_CYCLES_B1} cycles)")
print(f"  DMA read + write      : {dma_us:.2f} us  (m_axi HP0)")
print(f"  s_axilite + Python    : {axilite_us + python_misc_us:.1f} us")
print(f"  Round-trip estimate   : {roundtrip_us:.1f} us  ({roundtrip_us/BUDGET_US*100:.3f}% of budget)")
print(f"  Headroom              : {BUDGET_US/roundtrip_us:.0f}x")
print(f"  s_axilite is NOT on the data path -- audio moves via m_axi HP0.")
print("=" * 60)

# ---- cell 1: imports ----
import numpy as np
import sys, time, os
from pynq import Overlay, allocate, MMIO

sys.path.insert(0, '/home/xilinx/jupyter_notebooks/Preliminary_Project')
from tone_generator import load_wav, save_wav, SAMPLE_RATE
from audio_effects  import chain_hls

# ---- cell 2: build configurations ----
BASE = '/home/xilinx/jupyter_notebooks/Preliminary_Project/'

BUILDS = {
    'build1_pipeline': {
        'bit':     BASE + 'chain.bit',
        'hwh':     BASE + 'chain.hwh',
        'desc':    'Build 1 -- Sequential (3 loops, no DATAFLOW)',
        'ip_name': 'chain_top_0',
        'expected_cycles': 1469,
    },
    'build2_dataflow': {
        'bit':     BASE + 'chain2.bit',
        'hwh':     BASE + 'chain2.hwh',
        'desc':    'Build 2 -- DATAFLOW (concurrent stages, ping-pong BRAMs)',
        'ip_name': 'chain_top_2',   # renamed in Vivado block design
        'expected_cycles': 1469,   # latency = 1469 cycles (same as B1); II = 493 cycles (3x throughput)
        # DATAFLOW improves initiation interval, not single-chunk latency.
        # Wall-clock test (AP_START to AP_DONE, no overlap) will show ~14.69us = same as B1.
        # The 3x speedup only appears when invocations are pipelined (start N+1 before N done).
    },
}

available = {
    name: cfg for name, cfg in BUILDS.items()
    if os.path.exists(cfg['bit']) and os.path.exists(cfg['hwh'])
}

if not available:
    print("ERROR: no build files found in", BASE)
    print("  Build 1 needs: chain.bit  + chain.hwh")
    print("  Build 2 needs: chain2.bit + chain2.hwh")
    raise SystemExit

print(f"Found {len(available)} build(s):")
for name, cfg in available.items():
    print(f"  {name}: {cfg['desc']}")

# ---- cell 3: effect parameters ----
DIST_GAIN      = 3
TREM_RATE_HZ   = 5.0
TREM_RATE_STEP = int(TREM_RATE_HZ * 65536 / SAMPLE_RATE)
TREM_DEPTH_Q15 = 20000
DELAY_N        = 4800    # 100 ms
FEEDBACK_Q15   = 13000
MIX_Q15        = 16000

PARAMS = dict(
    dist_gain      = DIST_GAIN,
    trem_rate_step = TREM_RATE_STEP,
    trem_depth_q15 = TREM_DEPTH_Q15,
    delay_n        = DELAY_N,
    feedback_q15   = FEEDBACK_Q15,
    mix_q15        = MIX_Q15,
)

print(f"trem_rate_step={TREM_RATE_STEP}  delay={DELAY_N} samples ({DELAY_N/SAMPLE_RATE*1000:.0f} ms)")

# ---- cell 4: load test audio ----
# prefer a real WAV; fall back to the bundled test tone
wav_path = BASE + 'test_tone.wav'
if os.path.exists(wav_path):
    audio_full = load_wav(wav_path)
    print(f"Loaded {wav_path}: {len(audio_full)} samples ({len(audio_full)/SAMPLE_RATE:.2f}s)")
else:
    # generate a simple 440 Hz sine for testing
    t = np.arange(SAMPLE_RATE * 3) / SAMPLE_RATE
    audio_full = (np.sin(2 * np.pi * 440 * t) * 26000).astype(np.int16)
    print(f"test_tone.wav not found -- using generated 440 Hz sine ({len(audio_full)} samples)")

num_chunks = len(audio_full) // NUM_SAMPLES
audio_full = audio_full[:num_chunks * NUM_SAMPLES]   # trim to whole chunks
print(f"{num_chunks} chunks of {NUM_SAMPLES} samples each")

# ---- cell 5: test helpers ----
def run_one_chunk(ip, mem_ctrl, in_buf, out_buf, chunk, params):
    """Load one chunk, fire the IP, wait for AP_DONE, return (output, elapsed_us)."""
    in_buf[:] = chunk
    in_buf.flush()
    for k, v in params.items():
        setattr(ip.register_map, k, v)
    ip.register_map.CTRL.AP_START = 1
    t0 = time.perf_counter()
    while not ip.register_map.CTRL.AP_DONE:
        if time.perf_counter() - t0 > 2.0:
            raise TimeoutError("AP_DONE timed out -- check m_axi_MEM connection (see BUILD2_GUIDE.md)")
    elapsed_us = (time.perf_counter() - t0) * 1e6
    out_buf.invalidate()
    return np.array(out_buf, dtype=np.int16), elapsed_us


def test_build(build_name, cfg):
    """Run all tests for one build. Returns a results dict."""
    print()
    print("=" * 60)
    print(f"  {build_name}")
    print(f"  {cfg['desc']}")
    print("=" * 60)

    # reload python reference NOW so it matches the fresh FPGA state at bitstream load.
    # both start at zero: phase=0, delay_buf=zeros. do NOT reload again during the tests --
    # let python state accumulate alongside the FPGA across all three test stages.
    import importlib, audio_effects as ae_mod
    importlib.reload(ae_mod)
    from audio_effects import chain_hls as _ref

    # load overlay
    print("Loading overlay...", end=' ', flush=True)
    ol = Overlay(cfg['bit'])
    print("done")
    print("IPs:", list(ol.ip_dict.keys()))

    ip       = getattr(ol, cfg['ip_name'])
    mem_ctrl = MMIO(0x80000000, 0x10000)

    in_buf  = allocate(shape=(NUM_SAMPLES,), dtype=np.int16)
    out_buf = allocate(shape=(NUM_SAMPLES,), dtype=np.int16)

    # write buffer addresses once
    mem_ctrl.write(0x10,  in_buf.physical_address        & 0xFFFFFFFF)
    mem_ctrl.write(0x14, (in_buf.physical_address >> 32) & 0xFFFFFFFF)
    mem_ctrl.write(0x1C,  out_buf.physical_address        & 0xFFFFFFFF)
    mem_ctrl.write(0x20, (out_buf.physical_address >> 32) & 0xFFFFFFFF)

    results = {
        'build': build_name,
        'desc':  cfg['desc'],
        'pass_single': False,
        'pass_continuity': False,
        'latencies_us': [],
        'max_diff': None,
        'mismatches': 0,
    }

    # ── test 1: single-chunk bit-exact match ─────────────────────────────────
    print("\n[Test 1] Single-chunk bit-exact match")
    chunk = audio_full[:NUM_SAMPLES].copy()
    try:
        hw_out, elapsed_us = run_one_chunk(ip, mem_ctrl, in_buf, out_buf, chunk, PARAMS)
    except TimeoutError as e:
        print(f"  FAIL: {e}")
        return results

    ref_out = _ref(chunk, **PARAMS)

    if np.array_equal(hw_out, ref_out):
        print(f"  PASS -- {NUM_SAMPLES}/{NUM_SAMPLES} samples match  ({elapsed_us:.1f} us)")
        results['pass_single'] = True
        results['max_diff'] = 0
    else:
        matches  = np.sum(hw_out == ref_out)
        max_diff = int(np.max(np.abs(hw_out.astype(int) - ref_out.astype(int))))
        diffs    = np.where(hw_out != ref_out)[0]
        print(f"  FAIL -- {matches}/{NUM_SAMPLES} match, max diff={max_diff}")
        print(f"  First mismatches at samples: {diffs[:8]}")
        results['max_diff']    = max_diff
        results['mismatches']  = len(diffs)

    results['latencies_us'].append(elapsed_us)

    # ── test 2: state continuity across 10 chunks ────────────────────────────
    # verifies that the LFO phase counter and delay buffer survive between calls
    # (they are static variables -- they must NOT reset on every function call)
    print("\n[Test 2] State continuity -- 10 consecutive chunks")
    CONT_CHUNKS = 10
    fpga_cont   = np.zeros(CONT_CHUNKS * NUM_SAMPLES, dtype=np.int16)
    ref_cont    = np.zeros(CONT_CHUNKS * NUM_SAMPLES, dtype=np.int16)
    all_match   = True

    # python state (_ref) already matches FPGA -- both have run exactly 1 chunk (Test 1).
    # continue from current state; do NOT reload.

    for i in range(CONT_CHUNKS):
        chunk = audio_full[i * NUM_SAMPLES : (i+1) * NUM_SAMPLES].copy()
        hw_out, elapsed_us = run_one_chunk(ip, mem_ctrl, in_buf, out_buf, chunk, PARAMS)
        ref_out = _ref(chunk, **PARAMS)
        fpga_cont[i*NUM_SAMPLES:(i+1)*NUM_SAMPLES] = hw_out
        ref_cont [i*NUM_SAMPLES:(i+1)*NUM_SAMPLES] = ref_out
        results['latencies_us'].append(elapsed_us)
        if not np.array_equal(hw_out, ref_out):
            all_match = False
            print(f"  chunk {i}: MISMATCH (max diff {int(np.max(np.abs(hw_out.astype(int)-ref_out.astype(int))))})")

    if all_match:
        print(f"  PASS -- all {CONT_CHUNKS} chunks bit-exact  (LFO and delay state continuous)")
        results['pass_continuity'] = True
    else:
        print(f"  FAIL -- some chunks differ (likely state reset between calls)")
        # check if a state reset is the pattern: chunk 0 matches but later ones drift
        ch0_match = np.array_equal(fpga_cont[:NUM_SAMPLES], ref_cont[:NUM_SAMPLES])
        print(f"  Chunk 0 matches: {ch0_match} -- {'state resets each call' if not ch0_match else 'state drifts after chunk 0'}")

    # ── test 3: latency measurement over 50 chunks ───────────────────────────
    print("\n[Test 3] Latency measurement -- 50 chunks")
    TIMING_CHUNKS = 50
    timing_samples = []
    for i in range(TIMING_CHUNKS):
        chunk = audio_full[(i % num_chunks) * NUM_SAMPLES : (i % num_chunks + 1) * NUM_SAMPLES].copy()
        _, elapsed_us = run_one_chunk(ip, mem_ctrl, in_buf, out_buf, chunk, PARAMS)
        timing_samples.append(elapsed_us)

    med_us  = float(np.median(timing_samples))
    mean_us = float(np.mean(timing_samples))
    min_us  = float(np.min(timing_samples))
    max_us  = float(np.max(timing_samples))
    results['latencies_us'] = timing_samples
    results['med_us']  = med_us
    results['mean_us'] = mean_us
    print(f"  Median: {med_us:.1f} us   Mean: {mean_us:.1f} us   Min: {min_us:.1f} us   Max: {max_us:.1f} us")
    print(f"  ({med_us/BUDGET_US*100:.3f}% of 10 ms budget)")

    # clean up
    in_buf.freebuffer()
    out_buf.freebuffer()

    print()
    print(f"  Test 1 (bit-exact, 1 chunk):  {'PASS' if results['pass_single']     else 'FAIL'}")
    print(f"  Test 2 (continuity, 10 chunk): {'PASS' if results['pass_continuity'] else 'FAIL'}")
    print(f"  Test 3 (latency, 50 chunk):   {med_us:.1f} us median")

    return results


# ---- cell 6: run all available builds ----
all_results = {}
for name, cfg in available.items():
    all_results[name] = test_build(name, cfg)

# ---- cell 7: comparison table (shown if both builds ran) ----
if len(all_results) == 2:
    b1 = all_results.get('build1_pipeline')
    b2 = all_results.get('build2_dataflow')

    if b1 and b2 and 'med_us' in b1 and 'med_us' in b2:
        speedup = b1['med_us'] / b2['med_us'] if b2['med_us'] > 0 else float('nan')
        print()
        print("=" * 60)
        print("  BUILD 1 vs BUILD 2 COMPARISON")
        print("=" * 60)
        print(f"  {'Metric':<30} {'Build 1':>12} {'Build 2':>12}")
        print(f"  {'-'*30} {'-'*12} {'-'*12}")
        print(f"  {'Median latency (us)':<30} {b1['med_us']:>11.1f}  {b2['med_us']:>11.1f}")
        print(f"  {'% of 10ms budget':<30} {b1['med_us']/BUDGET_US*100:>10.3f}%  {b2['med_us']/BUDGET_US*100:>10.3f}%")
        print(f"  {'Speedup (B1/B2)':<30} {'—':>12} {speedup:>11.2f}x")
        print(f"  {'Bit-exact match':<30} {'PASS' if b1['pass_single'] else 'FAIL':>12} {'PASS' if b2['pass_single'] else 'FAIL':>12}")
        print(f"  {'State continuity':<30} {'PASS' if b1['pass_continuity'] else 'FAIL':>12} {'PASS' if b2['pass_continuity'] else 'FAIL':>12}")
        print("=" * 60)
        print(f"  Theoretical Build 2 speedup (DATAFLOW ideal): ~3x")
        print(f"  Actual measured speedup:  {speedup:.2f}x")
        if speedup < 1.5:
            print("  Note: lower-than-expected gain likely due to static state in")
            print("  do_tremolo/do_delay limiting DATAFLOW overlap. See synthesis report.")
        elif speedup >= 2.5:
            print("  DATAFLOW working well -- close to theoretical 3x.")
        print("=" * 60)

# ---- cell 7b: save results to text file ----
os.makedirs(BASE + 'output', exist_ok=True)
results_path = BASE + 'output/test_results.txt'

with open(results_path, 'w') as f:
    import time as _time
    f.write("FPGA Musician -- Hardware Test Results\n")
    f.write(f"Date: {_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("=" * 62 + "\n\n")

    for name, res in all_results.items():
        f.write(f"{name}\n{res['desc']}\n")
        f.write("-" * 42 + "\n")
        f.write(f"  Bit-exact match (1 chunk):    {'PASS' if res.get('pass_single')     else 'FAIL'}\n")
        f.write(f"  State continuity (10 chunks): {'PASS' if res.get('pass_continuity') else 'FAIL'}\n")
        if 'med_us' in res:
            f.write(f"  Latency median:  {res['med_us']:.1f} us\n")
            f.write(f"  Latency mean:    {res.get('mean_us', 0):.1f} us\n")
            f.write(f"  % of 10ms budget: {res['med_us'] / BUDGET_US * 100:.3f}%\n")
        f.write("\n")

    f.write("HLS SYNTHESIS REFERENCE (from csynth.rpt)\n")
    f.write("-" * 42 + "\n")
    f.write(f"  {'Metric':<22} {'Build 1':>12} {'Build 2':>12}\n")
    f.write(f"  {'Latency (cycles)':<22} {'1,469':>12} {'1,469':>12}\n")
    f.write(f"  {'Interval / II':<22} {'1,470':>12} {'493':>12}\n")
    f.write(f"  {'BRAM':<22} {'19 (4%)':>12} {'19 (4%)':>12}\n")
    f.write(f"  {'DSP':<22} {'12 (3%)':>12} {'12 (3%)':>12}\n")
    f.write(f"  {'LUT':<22} {'3,249 (4%)':>12} {'3,911 (5%)':>12}\n")
    f.write(f"  {'FF':<22} {'2,246 (1%)':>12} {'3,134 (2%)':>12}\n")
    f.write("\n")
    f.write("  Note: DATAFLOW improved II (throughput) ~3x, latency unchanged.\n")
    f.write("  Wall-clock test (wait AP_DONE per chunk) measures latency, not II.\n")
    f.write("  Expect similar measured times for both builds.\n\n")

    if 'build1_pipeline' in all_results and 'build2_dataflow' in all_results:
        b1 = all_results['build1_pipeline']
        b2 = all_results['build2_dataflow']
        if 'med_us' in b1 and 'med_us' in b2:
            speedup = b1['med_us'] / b2['med_us'] if b2['med_us'] > 0 else float('nan')
            f.write("MEASURED COMPARISON\n")
            f.write("-" * 42 + "\n")
            f.write(f"  {'Metric':<30} {'Build 1':>10} {'Build 2':>10}\n")
            f.write(f"  {'Median latency (us)':<30} {b1['med_us']:>9.1f}  {b2['med_us']:>9.1f}\n")
            f.write(f"  {'% of 10ms budget':<30} {b1['med_us']/BUDGET_US*100:>9.3f}%  {b2['med_us']/BUDGET_US*100:>9.3f}%\n")
            f.write(f"  {'Measured speedup (B1/B2)':<30} {'—':>10} {speedup:>9.2f}x\n")
            f.write(f"  {'Bit-exact match':<30} {'PASS' if b1['pass_single'] else 'FAIL':>10} {'PASS' if b2['pass_single'] else 'FAIL':>10}\n")
            f.write(f"  {'State continuity':<30} {'PASS' if b1['pass_continuity'] else 'FAIL':>10} {'PASS' if b2['pass_continuity'] else 'FAIL':>10}\n")

print(f"\nResults saved to: {results_path}")

# ---- cell 8: save output WAV files ----
print("\nSaving output WAVs...")
os.makedirs(BASE + 'output', exist_ok=True)

for name, res in all_results.items():
    if not res.get('pass_single'):
        continue
    # re-run full WAV through the build (use the overlay that's still loaded if only one)
    # for a clean save, just use the python reference (FPGA verified bit-exact)
    print(f"  {name}: test passed, use python reference for full-file output")

# python reference full file (always available, bit-exact with FPGA)
ref_full = np.zeros(len(audio_full), dtype=np.int16)
import importlib, audio_effects as ae_mod
importlib.reload(ae_mod)
from audio_effects import chain_hls as chain_hls_ref

for i in range(num_chunks):
    chunk = audio_full[i*NUM_SAMPLES:(i+1)*NUM_SAMPLES]
    ref_full[i*NUM_SAMPLES:(i+1)*NUM_SAMPLES] = chain_hls_ref(chunk, **PARAMS)

save_wav(BASE + 'output/chain_reference_out.wav', ref_full)
print(f"  Saved: output/chain_reference_out.wav")

# ---- cell 9: plot (optional -- requires matplotlib) ----
try:
    import matplotlib.pyplot as plt

    t = np.arange(NUM_SAMPLES * 3) / SAMPLE_RATE * 1000
    fig, axes = plt.subplots(len(all_results) + 1, 1,
                             figsize=(12, 3 * (len(all_results) + 1)),
                             sharex=True)
    if len(all_results) == 1:
        axes = [axes, None]

    axes[0].plot(t, audio_full[:NUM_SAMPLES*3], color='#94A3B8', lw=1.0, label='dry input')
    axes[0].set_title('Input (dry)', fontsize=10)
    axes[0].set_ylabel('amplitude (Q15)')
    axes[0].legend(loc='upper right', fontsize=8)

    for ax, (name, res) in zip(axes[1:], all_results.items()):
        if ax is None:
            continue
        # show reference (bit-exact with FPGA)
        ax.plot(t, ref_full[:NUM_SAMPLES*3], color='#2D6A4F', lw=1.2, label=f'{name} output')
        ax.set_title(f"{name} -- {'PASS' if res.get('pass_single') else 'FAIL'}, "
                     f"latency {res.get('med_us', 0):.1f} us median", fontsize=10)
        ax.set_ylabel('amplitude (Q15)')
        ax.legend(loc='upper right', fontsize=8)

    axes[-1].set_xlabel('time (ms)')
    plt.tight_layout()
    plt.savefig(BASE + 'output/build_comparison.png', dpi=150, bbox_inches='tight')
    plt.show()
    print("Plot saved to output/build_comparison.png")
except Exception as e:
    print(f"Plot skipped: {e}")
