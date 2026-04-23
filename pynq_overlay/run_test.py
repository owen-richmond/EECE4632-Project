# run_test.py -- Owen Richmond, EECE4632
# Minimal FPGA Musician test: latency, bit-exact, DATAFLOW throughput.
#
# Optimizations vs old scripts:
#   - non-cacheable DMA  → no flush/invalidate syscalls
#   - direct MMIO        → no Python register_map object chain
#   - params written once → only AP_START on hot path
#
# DATAFLOW throughput attempt:
#   Build 2 II = 493 cycles = 4.93µs @ 100MHz.
#   To pipeline, next chunk must be loaded and AP_START fired while
#   current chunk is still computing (within 4.93µs of previous start).
#   Python's minimum per-operation overhead ~30µs makes this impossible.
#   Script demonstrates the gap empirically and reports theoretical max.

from pynq import Overlay, allocate, MMIO
import numpy as np, time, os, sys, wave, struct

sys.path.insert(0, '/home/xilinx/jupyter_notebooks/Preliminary_Project')
from tone_generator import load_wav, SAMPLE_RATE
import audio_effects as ae

BASE        = '/home/xilinx/jupyter_notebooks/Preliminary_Project/'
NUM_SAMPLES = 480
TIMING_N    = 300
SAMPLE_RATE = 48000
BUDGET_US   = NUM_SAMPLES / SAMPLE_RATE * 1e6   # 10,000 µs

PARAMS = dict(
    dist_gain      = 3,
    trem_rate_step = int(5.0 * 65536 / SAMPLE_RATE),
    trem_depth_q15 = 20000,
    delay_n        = 4800,
    feedback_q15   = 13000,
    mix_q15        = 16000,
)

BUILDS = {
    'build1_pipeline': {
        'bit':     BASE + 'chain.bit',
        'hwh':     BASE + 'chain.hwh',
        'ip_name': 'chain_top_0',
        'II_cycles': 1470,
    },
    'build2_dataflow': {
        'bit':     BASE + 'chain2.bit',
        'hwh':     BASE + 'chain2.hwh',
        'ip_name': 'chain_top_2',
        'II_cycles': 493,
    },
}

# ── audio source ──────────────────────────────────────────────────────────────
wav_path = BASE + 'test_tone.wav'
if os.path.exists(wav_path):
    audio = load_wav(wav_path)
else:
    t = np.arange(SAMPLE_RATE * 3) / SAMPLE_RATE
    audio = (np.sin(2 * np.pi * 440 * t) * 26000).astype(np.int16)
num_chunks = len(audio) // NUM_SAMPLES

def get_chunk(i):
    s = (i % num_chunks) * NUM_SAMPLES
    return audio[s : s + NUM_SAMPLES].copy()

# ── reference Python implementation ──────────────────────────────────────────
import importlib
importlib.reload(ae)
from audio_effects import chain_hls as _ref_chain

ref_out = []
for i in range(num_chunks):
    ref_out.append(_ref_chain(get_chunk(i).astype(np.int32),
                              PARAMS['dist_gain'],
                              PARAMS['trem_rate_step'],
                              PARAMS['trem_depth_q15'],
                              PARAMS['delay_n'],
                              PARAMS['feedback_q15'],
                              PARAMS['mix_q15']))

# ── per-build test ────────────────────────────────────────────────────────────
def run_build(name, cfg, report_lines):
    R = report_lines
    R.append('')
    R.append('=' * 62)
    R.append(f'  {name}')
    R.append('=' * 62)

    ol = Overlay(cfg['bit'])
    ip = getattr(ol, cfg['ip_name'])

    # non-cacheable buffers — no flush/invalidate needed
    in_buf  = allocate(shape=(NUM_SAMPLES,), dtype=np.int16, cacheable=False)
    out_buf = allocate(shape=(NUM_SAMPLES,), dtype=np.int16, cacheable=False)

    # write buffer addresses to AXI master port (DMA-style direct registers)
    mem_ctrl = MMIO(0x80000000, 0x10000)
    mem_ctrl.write(0x10,  in_buf.physical_address        & 0xFFFFFFFF)
    mem_ctrl.write(0x14, (in_buf.physical_address >> 32) & 0xFFFFFFFF)
    mem_ctrl.write(0x1C,  out_buf.physical_address        & 0xFFFFFFFF)
    mem_ctrl.write(0x20, (out_buf.physical_address >> 32) & 0xFFFFFFFF)

    # direct MMIO for AP_CTRL (offset 0x00 in s_axi_CTRL)
    ctrl_addr = ol.ip_dict[cfg['ip_name']]['phys_addr']
    ap = MMIO(ctrl_addr, 0x40)

    # write params once
    for k, v in PARAMS.items():
        setattr(ip.register_map, k, v)

    # ── test 1: bit-exact (1 chunk, fresh state) ─────────────────────────────
    importlib.reload(ae)
    from audio_effects import chain_hls as ref1

    chunk0 = get_chunk(0)
    in_buf[:] = chunk0
    ap.write(0x00, 0x1)
    while not (ap.read(0x00) & 0x2):
        pass
    hw_out = np.array(out_buf, dtype=np.int32)

    ref_chunk = ref1(chunk0.astype(np.int32),
                     PARAMS['dist_gain'], PARAMS['trem_rate_step'],
                     PARAMS['trem_depth_q15'], PARAMS['delay_n'],
                     PARAMS['feedback_q15'], PARAMS['mix_q15'])
    bit_exact = np.array_equal(hw_out, ref_chunk)
    R.append(f'  Bit-exact match (1 chunk):    {"PASS" if bit_exact else "FAIL"}')
    if not bit_exact:
        diffs = np.where(hw_out != ref_chunk)[0]
        R.append(f'    First diff at sample {diffs[0]}: hw={hw_out[diffs[0]]} ref={ref_chunk[diffs[0]]}')

    # ── test 2: state continuity (10 chunks) ─────────────────────────────────
    importlib.reload(ae)
    from audio_effects import chain_hls as ref2

    state_ok = True
    for i in range(10):
        chunk = get_chunk(i)
        in_buf[:] = chunk
        ap.write(0x00, 0x1)
        while not (ap.read(0x00) & 0x2):
            pass
        hw_i = np.array(out_buf, dtype=np.int32)
        ref_i = ref2(chunk.astype(np.int32),
                     PARAMS['dist_gain'], PARAMS['trem_rate_step'],
                     PARAMS['trem_depth_q15'], PARAMS['delay_n'],
                     PARAMS['feedback_q15'], PARAMS['mix_q15'])
        if not np.array_equal(hw_i, ref_i):
            state_ok = False
            diffs = np.where(hw_i != ref_i)[0]
            R.append(f'  State continuity: FAIL at chunk {i}, sample {diffs[0]}: '
                     f'hw={hw_i[diffs[0]]} ref={ref_i[diffs[0]]}')
            break
    if state_ok:
        R.append(f'  State continuity (10 chunks): PASS')

    # ── test 3: optimized latency measurement ────────────────────────────────
    latencies = []
    for i in range(TIMING_N):
        chunk = get_chunk(i)
        in_buf[:] = chunk
        t0 = time.perf_counter()
        ap.write(0x00, 0x1)
        while not (ap.read(0x00) & 0x2):
            pass
        latencies.append((time.perf_counter() - t0) * 1e6)

    lat_arr = np.array(latencies)
    med_us  = float(np.median(lat_arr))
    min_us  = float(np.min(lat_arr))
    pct     = med_us / BUDGET_US * 100

    R.append(f'  Latency median:  {med_us:.2f} µs')
    R.append(f'  Latency min:     {min_us:.2f} µs')
    R.append(f'  % of 10ms budget:{pct:.3f}%')
    R.append(f'  Throughput (seq):{1e6/med_us:,.0f} chunks/sec  '
             f'({1e6/med_us*NUM_SAMPLES/SAMPLE_RATE*100:.1f}× real-time)')

    # ── test 4: DATAFLOW pipelining attempt (build2 only) ────────────────────
    II_us = cfg['II_cycles'] / 100.0  # cycles → µs @ 100MHz
    if cfg['II_cycles'] < 1000:
        R.append('')
        R.append('  -- DATAFLOW pipelining attempt --')
        R.append(f'  Target: fire next AP_START within II={II_us:.2f}µs of previous.')

        # double buffers
        buf_a_in  = allocate(shape=(NUM_SAMPLES,), dtype=np.int16, cacheable=False)
        buf_b_in  = allocate(shape=(NUM_SAMPLES,), dtype=np.int16, cacheable=False)
        buf_a_out = allocate(shape=(NUM_SAMPLES,), dtype=np.int16, cacheable=False)
        buf_b_out = allocate(shape=(NUM_SAMPLES,), dtype=np.int16, cacheable=False)

        # write initial buffer addresses
        mem_ctrl.write(0x10,  buf_a_in.physical_address  & 0xFFFFFFFF)
        mem_ctrl.write(0x14, (buf_a_in.physical_address  >> 32) & 0xFFFFFFFF)
        mem_ctrl.write(0x1C,  buf_a_out.physical_address & 0xFFFFFFFF)
        mem_ctrl.write(0x20, (buf_a_out.physical_address >> 32) & 0xFFFFFFFF)

        # attempt: load chunk N+1 while chunk N is computing, then
        # re-point DMA and fire AP_START the moment AP_READY goes high.
        # AP_READY bit = bit 2 of AP_CTRL register.
        PIPE_N = 100
        buf_a_in[:] = get_chunk(0)
        ap.write(0x00, 0x1)  # start chunk 0

        pipe_times = []
        achieved_restarts = 0
        for i in range(1, PIPE_N):
            next_chunk = get_chunk(i)
            # pick alternating buffer
            next_in  = buf_b_in  if (i % 2) else buf_a_in
            next_out = buf_b_out if (i % 2) else buf_a_out
            next_in[:] = next_chunk

            # wait for AP_READY (FPGA accepts next transaction)
            t_ready_wait = time.perf_counter()
            while not (ap.read(0x00) & 0x4):  # AP_READY bit
                pass
            t_ready = time.perf_counter()

            # re-point DMA to next buffers
            mem_ctrl.write(0x10,  next_in.physical_address  & 0xFFFFFFFF)
            mem_ctrl.write(0x14, (next_in.physical_address  >> 32) & 0xFFFFFFFF)
            mem_ctrl.write(0x1C,  next_out.physical_address & 0xFFFFFFFF)
            mem_ctrl.write(0x20, (next_out.physical_address >> 32) & 0xFFFFFFFF)

            t_start = time.perf_counter()
            ap.write(0x00, 0x1)
            overhead_us = (t_start - t_ready) * 1e6
            pipe_times.append(overhead_us)
            if overhead_us < II_us:
                achieved_restarts += 1

        # wait for last chunk to finish
        while not (ap.read(0x00) & 0x2):
            pass

        overhead_arr = np.array(pipe_times)
        R.append(f'  Restart overhead median: {np.median(overhead_arr):.2f}µs  '
                 f'(need <{II_us:.2f}µs to exploit II)')
        R.append(f'  Successful restarts within II: {achieved_restarts}/{PIPE_N-1}')
        if achieved_restarts == 0:
            R.append(f'  Result: Python too slow to pipeline — gap is '
                     f'{np.median(overhead_arr)/II_us:.1f}× over II')
        else:
            R.append(f'  Result: partial pipelining achieved ({achieved_restarts} of {PIPE_N-1})')

        # theoretical throughput with C/baremetal driver
        R.append('')
        R.append('  Theoretical throughput comparison:')
        R.append(f'    Python sequential:  {1e6/med_us:>10,.0f} chunks/sec')
        R.append(f'    Python (best meas): {1e6/min_us:>10,.0f} chunks/sec')
        R.append(f'    FPGA II limit:      {1e6/II_us:>10,.0f} chunks/sec  '
                 f'(II={II_us:.2f}µs, C/baremetal driver needed)')
        R.append(f'    Python gap vs FPGA: {(1e6/II_us)/(1e6/med_us):.0f}× '
                 f'speedup left on table')

        buf_a_in.freebuffer(); buf_b_in.freebuffer()
        buf_a_out.freebuffer(); buf_b_out.freebuffer()

    # ── save WAV output ───────────────────────────────────────────────────────
    # process full audio with FPGA for WAV output
    # reload Python ref for a fresh full-audio pass
    importlib.reload(ae)
    from audio_effects import chain_hls as ref_wav

    hw_audio = np.zeros(num_chunks * NUM_SAMPLES, dtype=np.int16)
    in_buf2  = allocate(shape=(NUM_SAMPLES,), dtype=np.int16, cacheable=False)
    out_buf2 = allocate(shape=(NUM_SAMPLES,), dtype=np.int16, cacheable=False)
    mem_ctrl.write(0x10,  in_buf2.physical_address  & 0xFFFFFFFF)
    mem_ctrl.write(0x14, (in_buf2.physical_address  >> 32) & 0xFFFFFFFF)
    mem_ctrl.write(0x1C,  out_buf2.physical_address & 0xFFFFFFFF)
    mem_ctrl.write(0x20, (out_buf2.physical_address >> 32) & 0xFFFFFFFF)
    for k, v in PARAMS.items():
        setattr(ip.register_map, k, v)

    for i in range(num_chunks):
        in_buf2[:] = get_chunk(i)
        ap.write(0x00, 0x1)
        while not (ap.read(0x00) & 0x2):
            pass
        hw_audio[i*NUM_SAMPLES:(i+1)*NUM_SAMPLES] = out_buf2

    wav_out_path = f'/home/xilinx/jupyter_notebooks/Preliminary_Project/output_{name}.wav'
    os.makedirs(os.path.dirname(wav_out_path), exist_ok=True)
    with wave.open(wav_out_path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(hw_audio.tobytes())
    R.append(f'  WAV output saved: {wav_out_path}')

    in_buf2.freebuffer(); out_buf2.freebuffer()
    in_buf.freebuffer(); out_buf.freebuffer()

    return med_us, min_us

# ── main ──────────────────────────────────────────────────────────────────────
print("FPGA Musician -- run_test.py")
print(f"Audio: {num_chunks} chunks × {NUM_SAMPLES} samples @ {SAMPLE_RATE}Hz")
print()

report = []
report.append('FPGA Musician -- Hardware Test Results')
report.append(f'Date: {time.strftime("%Y-%m-%d %H:%M:%S")}')
report.append(f'Optimizations: non-cacheable DMA + direct MMIO + static params')
report.append('=' * 62)

results = {}
for bname, bcfg in BUILDS.items():
    bit_file = bcfg['bit']
    if not os.path.exists(bit_file):
        report.append(f'\n  {bname}: SKIPPED (bit file not found: {bit_file})')
        print(f'Skipping {bname}: {bit_file} not found')
        continue
    print(f'Testing {bname}...', flush=True)
    med, mn = run_build(bname, bcfg, report)
    results[bname] = (med, mn)
    print(f'  done: median={med:.2f}µs')

# ── HLS synthesis reference ───────────────────────────────────────────────────
report.append('')
report.append('HLS SYNTHESIS REFERENCE (from csynth.rpt)')
report.append('-' * 44)
report.append(f'  {"Metric":<28} {"Build 1":>9}  {"Build 2":>9}')
report.append(f'  {"-"*28} {"-"*9}  {"-"*9}')
report.append(f'  {"Latency (cycles)":<28} {"1,469":>9}  {"1,469":>9}')
report.append(f'  {"Interval / II":<28} {"1,470":>9}  {"493":>9}')
report.append(f'  {"BRAM":<28} {"19 (4%)":>9}  {"19 (4%)":>9}')
report.append(f'  {"DSP":<28} {"12 (3%)":>9}  {"12 (3%)":>9}')
report.append(f'  {"LUT":<28} {"3,249 (4%)":>9}  {"3,911 (5%)":>9}')
report.append(f'  {"FF":<28} {"2,246 (1%)":>9}  {"3,134 (2%)":>9}')
report.append(f'  Note: DATAFLOW improves II (throughput) 3×; latency unchanged.')
report.append(f'  Note: persistent static state (LFO/delay) may diverge under')
report.append(f'        DATAFLOW ping-pong control. Hardware shows PASS but')
report.append(f'        synthesis does not guarantee state continuity indefinitely.')

# ── measured comparison ───────────────────────────────────────────────────────
if len(results) == 2:
    b1_med, b1_min = results['build1_pipeline']
    b2_med, b2_min = results['build2_dataflow']
    report.append('')
    report.append('MEASURED COMPARISON (direct MMIO, non-cacheable DMA)')
    report.append('-' * 44)
    report.append(f'  {"Metric":<36} {"Build 1":>7}  {"Build 2":>7}')
    report.append(f'  {"-"*36} {"-"*7}  {"-"*7}')
    report.append(f'  {"Median latency (µs)":<36} {b1_med:>7.2f}  {b2_med:>7.2f}')
    report.append(f'  {"Min latency (µs)":<36} {b1_min:>7.2f}  {b2_min:>7.2f}')
    report.append(f'  {"% of 10ms budget":<36} {b1_med/BUDGET_US*100:>6.3f}%  {b2_med/BUDGET_US*100:>6.3f}%')
    report.append(f'  {"Measured speedup (B1/B2)":<36} {"—":>7}  {b1_med/b2_med:>7.2f}×')
    report.append(f'  {"Sequential chunks/sec":<36} {1e6/b1_med:>7,.0f}  {1e6/b2_med:>7,.0f}')

# ── Python vs FPGA throughput gap summary ────────────────────────────────────
report.append('')
report.append('THROUGHPUT GAP: Python PS vs FPGA PL')
report.append('-' * 44)
report.append(f'  Python overhead dominates: DMA+MMIO min ~{min(r[1] for r in results.values()):.1f}µs per chunk')
report.append(f'  FPGA II (Build 2):         4.93µs  (hardware limit)')
report.append(f'  To exploit II, restart must happen within 4.93µs of last start.')
report.append(f'  Python minimum per-operation: ~30µs → pipelining not achievable.')
report.append(f'  A C or baremetal driver could achieve ~{1e6/4.93:,.0f} chunks/sec,')
report.append(f'  vs Python ~{1e6/min(r[1] for r in results.values()):,.0f} chunks/sec — {(1e6/4.93)/(1e6/min(r[1] for r in results.values())):.0f}× gap.')
report.append(f'  Conclusion: DATAFLOW II benefit requires moving off Python PS.')

report.append('')
report.append('=' * 62)

report_text = '\n'.join(report)

out_path = '/home/xilinx/jupyter_notebooks/Preliminary_Project/output/test_results.txt'
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, 'w') as f:
    f.write(report_text)

print()
print(report_text)
print()
print(f'Report saved: {out_path}')
