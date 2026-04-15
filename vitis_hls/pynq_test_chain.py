# pynq_test_chain.py -- Owen Richmond, EECE4632
# test notebook for chain_top IP (build 2 dataflow) on the AUP-ZU3
# runs full distortion->tremolo->delay pipeline, compares against python reference
# also plays audio in the browser so you can actually hear it

# ---- cell 1: imports ----
import numpy as np
import sys, time
from pynq import Overlay, allocate, MMIO

sys.path.insert(0, '/home/xilinx/jupyter_notebooks/Preliminary_Project')
from tone_generator import generate_tone, load_wav, save_wav, SAMPLE_RATE
from audio_effects  import chain_hls

# ---- cell 2: load the overlay (update path once you have the bitstream) ----
ol = Overlay('/home/xilinx/jupyter_notebooks/Preliminary_Project/chain.bit')
print("IPs found:", list(ol.ip_dict.keys()))

# ---- cell 3: grab AXI interfaces (same pattern as distortion build) ----
ip       = ol.chain_top_0        # s_axi_CTRL: all control params + AP_START/DONE
mem_ctrl = MMIO(0x80000000, 0x10000)   # s_axi_MEM: buffer addresses

# ---- cell 4: choose input -- either synthesized tone or loaded WAV ----
NUM_SAMPLES = 480
USE_WAV = False   # flip to True to load a real audio file instead

if USE_WAV:
    # load a WAV and grab one 10ms chunk from the middle of it
    # put your audio file on the board and update the path
    audio_full = load_wav('/home/xilinx/jupyter_notebooks/Preliminary_Project/sample.wav')
    start = len(audio_full) // 4   # grab from quarter-way in so it isnt silence
    in_data = audio_full[start : start + NUM_SAMPLES]
    if len(in_data) < NUM_SAMPLES:
        in_data = np.pad(in_data, (0, NUM_SAMPLES - len(in_data)))
else:
    # 440Hz sine at 0.8 amplitude, clean test tone
    in_data = generate_tone(440.0, NUM_SAMPLES / SAMPLE_RATE, amplitude=0.8)[:NUM_SAMPLES]

in_buf  = allocate(shape=(NUM_SAMPLES,), dtype=np.int16)
out_buf = allocate(shape=(NUM_SAMPLES,), dtype=np.int16)
in_buf[:] = in_data
print("input peak:", int(np.max(np.abs(in_buf))), "/ 32767")

# ---- cell 5: set effect parameters ----
DIST_GAIN      = 3       # 1=clean, 4=crunchy
TREM_RATE_HZ   = 5.0
TREM_RATE_STEP = int(TREM_RATE_HZ * 65536 / SAMPLE_RATE)  # ARM precomputes this
TREM_DEPTH_Q15 = 20000   # ~0.6 depth
DELAY_N        = 4800    # 100ms
FEEDBACK_Q15   = 13000   # ~0.4 feedback
MIX_Q15        = 16000   # ~0.49 wet

print(f"trem_rate_step={TREM_RATE_STEP}, delay={DELAY_N} samples ({DELAY_N/SAMPLE_RATE*1000:.0f}ms)")

# ---- cell 6: write buffer addresses (same as distortion pynq_test.py) ----
mem_ctrl.write(0x10, in_buf.physical_address & 0xffffffff)
mem_ctrl.write(0x14, (in_buf.physical_address >> 32) & 0xffffffff)
mem_ctrl.write(0x1C, out_buf.physical_address & 0xffffffff)
mem_ctrl.write(0x20, (out_buf.physical_address >> 32) & 0xffffffff)

# ---- cell 7: write effect parameters to s_axi_CTRL ----
# offsets from chain.hwh (read them from the hwh file after synthesis)
# these will match the order the tool assigns them -- double check against hwh
ip.register_map.dist_gain      = DIST_GAIN
ip.register_map.trem_rate_step = TREM_RATE_STEP
ip.register_map.trem_depth_q15 = TREM_DEPTH_Q15
ip.register_map.delay_n        = DELAY_N
ip.register_map.feedback_q15   = FEEDBACK_Q15
ip.register_map.mix_q15        = MIX_Q15

in_buf.flush()
ip.register_map.CTRL.AP_START = 1

t0 = time.time()
while not ip.register_map.CTRL.AP_DONE:
    if time.time() - t0 > 2.0:
        print("timed out -- check m_axi_MEM is connected in block design")
        break

out_buf.invalidate()
print("done! output peak:", int(np.max(np.abs(out_buf))), "/ 32767")

# ---- cell 8: compare against python reference (should be bit-exact) ----
golden = chain_hls(
    np.array(in_buf, dtype=np.int16),
    dist_gain=DIST_GAIN,
    trem_rate_step=TREM_RATE_STEP,
    trem_depth_q15=TREM_DEPTH_Q15,
    delay_n=DELAY_N,
    feedback_q15=FEEDBACK_Q15,
    mix_q15=MIX_Q15
)

if np.array_equal(out_buf, golden):
    print(f"PERFECT MATCH ({NUM_SAMPLES}/{NUM_SAMPLES} samples)")
else:
    matches = np.sum(out_buf == golden)
    diffs = np.where(out_buf != golden)[0]
    print(f"{matches}/{NUM_SAMPLES} samples match")
    print("first mismatches at samples:", diffs[:10])
    print("max difference:", int(np.max(np.abs(out_buf.astype(int) - golden.astype(int)))))

# ---- cell 9: listen in the browser ----
from IPython.display import Audio, display

# need float32 for IPython Audio, scale from Q15
def to_float(arr):
    return arr.astype(np.float32) / 32767.0

# play input (dry), fpga output, and python reference side by side
print("Dry input:")
display(Audio(to_float(in_buf), rate=SAMPLE_RATE))

print("FPGA output (chain_top):")
display(Audio(to_float(np.array(out_buf, dtype=np.int16)), rate=SAMPLE_RATE))

print("Python reference (should sound identical):")
display(Audio(to_float(golden), rate=SAMPLE_RATE))

# save wav files so you can compare in audacity too
save_wav('/home/xilinx/jupyter_notebooks/Preliminary_Project/output/fpga_chain_out.wav',
         np.array(out_buf, dtype=np.int16))
save_wav('/home/xilinx/jupyter_notebooks/Preliminary_Project/output/python_chain_out.wav',
         golden)

# ---- cell 10: plot ----
import matplotlib.pyplot as plt

t = np.arange(NUM_SAMPLES) / SAMPLE_RATE * 1000
plt.figure(figsize=(11, 5))
plt.plot(t, in_buf,  label='dry input',         alpha=0.7)
plt.plot(t, out_buf, label='fpga chain output', alpha=0.8, lw=1.2)
plt.plot(t, golden,  label='python reference',  linestyle='--', alpha=0.7)
plt.xlabel('time (ms)')
plt.ylabel('amplitude (Q15)')
plt.title(f'chain_top: dist(gain={DIST_GAIN}) -> tremolo(5Hz) -> delay(100ms) -- 440Hz A4')
plt.legend()
plt.tight_layout()
plt.savefig('/home/xilinx/jupyter_notebooks/Preliminary_Project/output/chain_fpga_vs_python.png',
            dpi=150, bbox_inches='tight')
plt.show()
