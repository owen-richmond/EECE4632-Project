# pynq_test.py -- Owen Richmond, EECE4632
# test notebook for distortion_top IP on the AUP-ZU3
#
# the IP has two separate AXI-Lite interfaces (found by reading distortion.hwh):
#   s_axi_control @ 0x80000000 -- holds the buffer address registers
#   s_axi_CTRL    @ 0x80010000 -- holds gain, AP_START, AP_DONE
# pynq's ip object only sees s_axi_CTRL, so we use MMIO for the other one

# ---- cell 1: imports ----
import numpy as np
import sys, time
from pynq import Overlay, allocate, MMIO

sys.path.insert(0, '/home/xilinx/jupyter_notebooks/EECE4632-Project')
from tone_generator import generate_tone
from audio_effects import distortion_hls

# ---- cell 2: load the overlay ----
ol = Overlay('/home/xilinx/jupyter_notebooks/EECE4632-Project/distortion.bit')
print("IPs found:", list(ol.ip_dict.keys()))

# ---- cell 3: grab both AXI interfaces ----
ip       = ol.distortion_top_0          # s_axi_CTRL: gain, AP_START, AP_DONE
mem_ctrl = MMIO(0x80000000, 0x10000)    # s_axi_control: buffer addresses

# ---- cell 4: allocate buffers ----
NUM_SAMPLES = 480

in_buf  = allocate(shape=(NUM_SAMPLES,), dtype=np.int16)
out_buf = allocate(shape=(NUM_SAMPLES,), dtype=np.int16)

dry = generate_tone(440.0, NUM_SAMPLES / 48000.0, amplitude=0.9)
in_buf[:] = dry[:NUM_SAMPLES]
print("input peak:", int(np.max(np.abs(in_buf))), "/ 32767")

# ---- cell 5: run the IP ----
GAIN = 4

# write buffer addresses to s_axi_control (64-bit address split into two 32-bit registers)
# offsets from hwh: in_samples_1=0x10, in_samples_2=0x14, out_samples_1=0x1C, out_samples_2=0x20
mem_ctrl.write(0x10, in_buf.physical_address & 0xffffffff)
mem_ctrl.write(0x14, (in_buf.physical_address >> 32) & 0xffffffff)
mem_ctrl.write(0x1C, out_buf.physical_address & 0xffffffff)
mem_ctrl.write(0x20, (out_buf.physical_address >> 32) & 0xffffffff)

in_buf.flush()   # push input data from CPU cache to DDR so the IP can read it

ip.register_map.gain = GAIN
ip.register_map.CTRL.AP_START = 1

t0 = time.time()
while not ip.register_map.CTRL.AP_DONE:
    if time.time() - t0 > 2.0:
        print("timed out -- check that m_axi_MEM is connected in the block design")
        break

out_buf.invalidate()  # flush CPU cache so we read what the IP actually wrote to DDR
print("done! output peak:", int(np.max(np.abs(out_buf))), "/ 32767")

# ---- cell 6: compare against python reference ----
golden = distortion_hls(np.array(in_buf, dtype=np.int16), gain=GAIN)

if np.array_equal(out_buf, golden):
    print(f"PERFECT MATCH ({NUM_SAMPLES}/{NUM_SAMPLES} samples)")
else:
    matches = np.sum(out_buf == golden)
    diffs = np.where(out_buf != golden)[0]
    print(f"{matches}/{NUM_SAMPLES} samples match")
    print("first mismatches at samples:", diffs[:10])
    print("max difference:", int(np.max(np.abs(out_buf.astype(int) - golden.astype(int)))))

# ---- cell 7: plot ----
import matplotlib.pyplot as plt

t = np.arange(NUM_SAMPLES) / 48000 * 1000
plt.figure(figsize=(10, 4))
plt.plot(t, in_buf,  label='input (dry)',     alpha=0.7)
plt.plot(t, out_buf, label='output (fpga)',   alpha=0.7)
plt.plot(t, golden,  label='golden (python)', linestyle='--', alpha=0.7)
plt.xlabel('time (ms)')
plt.ylabel('amplitude (Q15)')
plt.title(f'distortion_top: gain={GAIN}, 440Hz A4')
plt.legend()
plt.tight_layout()
plt.show()
