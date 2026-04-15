# pynq_test_chain.py -- Owen Richmond, EECE4632
# test notebook for chain_top IP on the AUP-ZU3
# processes a full WAV file in 480-sample chunks, compares against python reference

# ---- cell 1: imports ----
import numpy as np
import sys, time
from pynq import Overlay, allocate, MMIO

sys.path.insert(0, '/home/xilinx/jupyter_notebooks/Preliminary_Project')
from tone_generator import load_wav, save_wav, SAMPLE_RATE
from audio_effects  import chain_hls

# ---- cell 2: load overlay ----
ol = Overlay('/home/xilinx/jupyter_notebooks/Preliminary_Project/chain.bit')
print("IPs found:", list(ol.ip_dict.keys()))

# ---- cell 3: grab AXI interfaces ----
ip       = ol.chain_top_0
mem_ctrl = MMIO(0x80000000, 0x10000)   # s_axi_control: buffer addresses

# ---- cell 4: load audio, allocate DMA buffers ----
NUM_SAMPLES = 480

audio_full = load_wav('/home/xilinx/jupyter_notebooks/Preliminary_Project/test_tone.wav')

# pad to a multiple of NUM_SAMPLES
remainder = len(audio_full) % NUM_SAMPLES
if remainder:
    audio_full = np.pad(audio_full, (0, NUM_SAMPLES - remainder))
num_chunks = len(audio_full) // NUM_SAMPLES
print(f"loaded {len(audio_full)} samples ({len(audio_full)/SAMPLE_RATE:.2f}s), {num_chunks} chunks")

in_buf  = allocate(shape=(NUM_SAMPLES,), dtype=np.int16)
out_buf = allocate(shape=(NUM_SAMPLES,), dtype=np.int16)

# ---- cell 5: effect parameters ----
DIST_GAIN      = 3
TREM_RATE_HZ   = 5.0
TREM_RATE_STEP = int(TREM_RATE_HZ * 65536 / SAMPLE_RATE)
TREM_DEPTH_Q15 = 20000   # ~0.6 depth
DELAY_N        = 4800    # 100ms
FEEDBACK_Q15   = 13000   # ~0.4 feedback
MIX_Q15        = 16000   # ~0.49 wet
print(f"dist={DIST_GAIN}, trem={TREM_RATE_HZ}Hz depth={TREM_DEPTH_Q15}, delay={DELAY_N/SAMPLE_RATE*1000:.0f}ms")

# ---- cell 6: one-time setup (addresses + params don't change per chunk) ----
mem_ctrl.write(0x10, in_buf.physical_address & 0xffffffff)
mem_ctrl.write(0x14, (in_buf.physical_address >> 32) & 0xffffffff)
mem_ctrl.write(0x1C, out_buf.physical_address & 0xffffffff)
mem_ctrl.write(0x20, (out_buf.physical_address >> 32) & 0xffffffff)

ip.register_map.dist_gain      = DIST_GAIN
ip.register_map.trem_rate_step = TREM_RATE_STEP
ip.register_map.trem_depth_q15 = TREM_DEPTH_Q15
ip.register_map.delay_n        = DELAY_N
ip.register_map.feedback_q15   = FEEDBACK_Q15
ip.register_map.mix_q15        = MIX_Q15
print("setup done")

# ---- cell 7: multi-chunk loop (Claude) ----
# static state lives in BRAM on the FPGA between calls so effects stay
# continuous across chunks -- same reason chain_hls uses globals in python
fpga_out  = np.zeros(len(audio_full), dtype=np.int16)
golden    = np.zeros(len(audio_full), dtype=np.int16)

t_start = time.time()
for i in range(num_chunks):
    chunk = audio_full[i*NUM_SAMPLES : (i+1)*NUM_SAMPLES]
    in_buf[:] = chunk
    in_buf.flush()

    ip.register_map.CTRL.AP_START = 1
    t0 = time.time()
    while not ip.register_map.CTRL.AP_DONE:
        if time.time() - t0 > 2.0:
            print(f"timed out on chunk {i}")
            break
    out_buf.invalidate()

    fpga_out[i*NUM_SAMPLES : (i+1)*NUM_SAMPLES] = np.array(out_buf)
    golden  [i*NUM_SAMPLES : (i+1)*NUM_SAMPLES] = chain_hls(
        chunk, dist_gain=DIST_GAIN, trem_rate_step=TREM_RATE_STEP,
        trem_depth_q15=TREM_DEPTH_Q15, delay_n=DELAY_N,
        feedback_q15=FEEDBACK_Q15, mix_q15=MIX_Q15
    )

elapsed = time.time() - t_start
print(f"done: {num_chunks} chunks in {elapsed:.2f}s")

# ---- cell 8: compare ----
total = len(audio_full)
matches = int(np.sum(fpga_out == golden))
if matches == total:
    print(f"PERFECT MATCH ({total}/{total} samples across {num_chunks} chunks)")
else:
    diffs = np.where(fpga_out != golden)[0]
    print(f"{matches}/{total} samples match")
    print("first mismatches at samples:", diffs[:10])
    print("max difference:", int(np.max(np.abs(fpga_out.astype(int) - golden.astype(int)))))

# ---- cell 9: listen ----
from IPython.display import Audio, display

def to_float(arr):
    return arr.astype(np.float32) / 32767.0

print("Dry input:")
display(Audio(to_float(audio_full), rate=SAMPLE_RATE))
print("FPGA output:")
display(Audio(to_float(fpga_out), rate=SAMPLE_RATE))
print("Python reference:")
display(Audio(to_float(golden), rate=SAMPLE_RATE))

save_wav('/home/xilinx/jupyter_notebooks/Preliminary_Project/output/fpga_chain_out.wav',  fpga_out)
save_wav('/home/xilinx/jupyter_notebooks/Preliminary_Project/output/python_chain_out.wav', golden)

# ---- cell 10: plot one chunk from the middle ----
import matplotlib.pyplot as plt

mid = (num_chunks // 2) * NUM_SAMPLES
t = np.arange(NUM_SAMPLES) / SAMPLE_RATE * 1000
plt.figure(figsize=(11, 5))
plt.plot(t, audio_full[mid:mid+NUM_SAMPLES], label='dry input',        alpha=0.7)
plt.plot(t, fpga_out  [mid:mid+NUM_SAMPLES], label='fpga output',      alpha=0.8, lw=1.2)
plt.plot(t, golden    [mid:mid+NUM_SAMPLES], label='python reference',  linestyle='--', alpha=0.7)
plt.xlabel('time (ms)')
plt.ylabel('amplitude (Q15)')
plt.title(f'chain_top: chunk {num_chunks//2}/{num_chunks} -- dist={DIST_GAIN}, tremolo {TREM_RATE_HZ}Hz, delay 100ms')
plt.legend()
plt.tight_layout()
plt.savefig('/home/xilinx/jupyter_notebooks/Preliminary_Project/output/chain_fpga_vs_python.png',
            dpi=150, bbox_inches='tight')
plt.show()
