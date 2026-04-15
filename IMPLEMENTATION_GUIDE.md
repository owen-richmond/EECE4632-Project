# FPGA Musician -- Implementation Guide
**Owen Richmond, EECE4632 | AUP-ZU3-8GB | Vitis HLS 2024.1 | Vivado 2024.1 | PYNQ v3.1**

---

## Files at a Glance

```
python/
    audio_effects.py       reference implementations + HLS-matching functions
    tone_generator.py      WAV synthesis, load_wav, save_wav
    fpga_musician.py       demo script, run this first
vitis_hls/
    audio_effects.{h,cpp,_tb.cpp}    distortion_top (working, bitstream already built)
    build1_pipeline/                 chain_top, 3 sequential loops
    build2_dataflow/                 chain_top, 3 sub-functions + DATAFLOW pragma
pynq_overlay/
    distortion.bit / distortion.hwh  pre-built, ready to upload
```

---

## Step 0 -- Python Reference (no board needed)

```bash
pip install numpy matplotlib
cd python
python fpga_musician.py
```

Outputs WAV files and plots to `python/output/`. Open them in Audacity to verify the effects sound right before touching hardware.

---

## Step 1 -- Install Board Files

Copy `board-files/aup-zu3-8gb/` into Vivado's board repo:

```
Source:       EECE4632-Project\board-files\aup-zu3-8gb\
Destination:  C:\Xilinx\Vivado\2024.1\data\boards\board_files\aup-zu3-8gb\
```

Verify in Vivado Tcl console:
```tcl
get_board_parts *aup*
```
You should see `realdigital.org:aup-zu3-8gb:part0:1.0`. If nothing shows up, path is wrong.

---

## Step 2 -- Vitis HLS

Do this once for each of the three builds. The process is identical, only the source files and project name differ.

### New Project Setup

| Field | distortion_top | chain_build1 | chain_build2 |
|-------|---------------|--------------|--------------|
| Project name | `distortion_top` | `chain_build1` | `chain_build2` |
| Top function | `distortion_top` | `chain_top` | `chain_top` |
| Source file | `vitis_hls/audio_effects.cpp` | `vitis_hls/build1_pipeline/audio_effects.cpp` | `vitis_hls/build2_dataflow/audio_effects.cpp` |
| Testbench | `vitis_hls/audio_effects_tb.cpp` | `vitis_hls/build1_pipeline/audio_effects_tb.cpp` | `vitis_hls/build2_dataflow/audio_effects_tb.cpp` |

Put all three projects in the same workspace folder, e.g. `C:\Users\owens\vitis_workspace\`.

For all three:
- **Clock:** 10 ns (100 MHz)
- **Part:** xczu3eg-sfvc784-2-e (or pick AUP-ZU3-8GB from the Boards tab)
- **Solution name:** `hls`

### Run C Simulation

**Solution > Run C Simulation**

All tests should print `pass`. If anything fails, stop and fix the C++ before synthesizing.

### Run C Synthesis

**Solution > Run C Synthesis**

Takes 5-15 min. When done, check the synthesis report:
- `DISTORTION_LOOP / DIST_LOOP` should show `II=1`
- `DELAY_LOOP` will show `II=2` -- this is expected (BRAM read latency)
- Note the total **Latency** and **BRAM** numbers for Build 1 vs Build 2 comparison

> Build 2 may show `WARNING: [SYNCHK 200-53]` about static variables in DATAFLOW sub-functions. This is expected and doesn't break the design -- see troubleshooting.

### Export RTL

**Solution > Export RTL**

Format: IP Catalog. Exported to `<project>/hls/impl/`. Note this path for Vivado.

---

## Step 3 -- Vivado Block Design

> The distortion bitstream already exists in `pynq_overlay/`. Skip to Step 4 if you just want to test distortion on the board. You need this step for the chain builds.

### Create Project

**File > Project > New**

- Name: `distortion_project` or `chain_project`
- Board: AUP-ZU3-8GB (from Boards tab)
- RTL Project, no sources yet

### Add IP Repository

**Tools > Settings > IP > Repository > +**

Point it at `<vitis_workspace>/<project_name>/hls/impl/` (the `impl` folder, not the `ip` subfolder inside it).

### Block Design

1. **IP Integrator > Create Block Design**, give it a name
2. Add **Zynq UltraScale+ MPSoC** > click Run Block Automation (check "Apply Board Preset")
3. Add your HLS IP (`distortion_top` or `chain_top`) from the + menu
4. Click **Run Connection Automation**, check all boxes, click OK
5. Run Connection Automation a second time if the banner appears again
6. **Tools > Validate Design** -- fix any errors

### Generate Bitstream

**Program and Debug > Generate Bitstream** -- runs synthesis, implementation, bitstream (~30-45 min total).

### Export Files

After bitstream generation:
- `.bit` is in `<project>.runs/impl_1/<wrapper_name>.bit`
- `.hwh` is in `<project>.gen/sources_1/bd/<bd_name>/hw_handoff/<bd_name>.hwh`

Rename both to match (`distortion.bit` / `distortion.hwh` or `chain.bit` / `chain.hwh`) and put them in `pynq_overlay/`.

---

## Step 4 -- PYNQ Board Setup

### Flash SD Card

Download the AUP-ZU3 PYNQ v3.1 image from [pynq.io/boards.html](http://www.pynq.io/boards.html).
Flash to a microSD card with balenaEtcher.

### Boot

1. Insert SD card, set BOOT switch to **SD**
2. Power via USB-C (9V @ 3A)
3. Wait ~45 sec. Boot is complete when: ON LED on, LED1 heartbeating, DONE LED solid, then user LEDs flash.

### Connect

**USB-C Ethernet Gadget (easiest):** one USB-C cable from the board's OTG port to your PC. Windows installs a virtual Ethernet adapter. Browse to `http://192.168.3.1/lab`.

**Regular Ethernet:** board gets a DHCP address. Find it with `arp -a` on Windows. `192.168.3.1` won't work in this mode.

Login: `xilinx` / `xilinx`

### Upload Files

In JupyterLab, create `/home/xilinx/jupyter_notebooks/EECE4632-Project/` and upload:
- `python/` folder (all files)
- `pynq_overlay/distortion.bit` and `distortion.hwh` (and chain files when ready)
- `vitis_hls/pynq_test.py` and `pynq_test_chain.py`

Or use SCP:
```bash
scp -r python/ xilinx@192.168.3.1:/home/xilinx/jupyter_notebooks/EECE4632-Project/
scp pynq_overlay/distortion.bit pynq_overlay/distortion.hwh xilinx@192.168.3.1:/home/xilinx/jupyter_notebooks/EECE4632-Project/
```

Create the output directory on the board:
```bash
mkdir -p /home/xilinx/jupyter_notebooks/EECE4632-Project/output
```

---

## Step 5 -- Run Tests

### distortion_top test

Create a new Jupyter notebook in the `EECE4632-Project/` folder. Paste cells from `pynq_test.py` one block at a time (each `# ---- cell N ----` comment is one cell).

Expected result: `PERFECT MATCH (480/480 samples)` and a graph saved to `output/distortion_fpga_vs_python.png`.

### chain_top test

Same process with `pynq_test_chain.py` and `chain.bit` / `chain.hwh`.

Expected result: `PERFECT MATCH (480/480 samples)` and `output/chain_fpga_vs_python.png`.

**Parameter reference:**
- `DIST_GAIN`: 1 = clean, 4 = crunchy
- `TREM_RATE_STEP`: `int(rate_hz * 65536 / 48000)` -- e.g. 5 Hz = 7
- `DELAY_N`: samples -- e.g. 100 ms = 4800
- Q15 fractions: `int(fraction * 32767)` -- e.g. 0.4 feedback = 13107

---

## Troubleshooting

**"No IP found in repository"** -- Vivado needs to point at `<project>/hls/impl/`, not the `ip/` subfolder inside it. Also check that you ran Export RTL in Vitis HLS first.

**AP_DONE times out** -- `m_axi_MEM` isn't connected in the block design. Enable HP0 on the Zynq PS (double-click PS block > PS-PL Configuration > HP Slave AXI Interface > enable S AXI HP0 FPD), then re-run Connection Automation.

**MMIO addresses wrong** -- Open the `.hwh` as text, search for `in_samples` to find the `ADDRESS_OFFSET` values. The defaults (0x10, 0x14, 0x1C, 0x20) came from the original build. If you rebuilt from scratch they may differ.

**Build 2 DATAFLOW warnings** -- `WARNING: [SYNCHK 200-53]` about static variables is expected. The design still compiles and produces correct output. The latency improvement may be less than ideal.

**Overlay loads but IP list is empty** -- `.hwh` is missing or doesn't match the `.bit`. They must be from the same Vivado run.

**Timing violation (WNS < 0)** -- Lower clock to 50 MHz in the block design and re-run implementation. The distortion and tremolo stages are fine at 100 MHz; the delay BRAM path is most likely to be marginal.

**Results not bit-exact** -- Verify you're calling `distortion_hls()` not `distortion()` (the regular one normalizes the peak, which the FPGA doesn't do). For the chain, verify `chain_hls()` state globals haven't been called previously in the same Python session with different parameters.

**ImportError for tone_generator or audio_effects on the board** -- The `sys.path.insert` in the test scripts points to `/home/xilinx/jupyter_notebooks/EECE4632-Project/python`. The `python/` folder needs to be there with that exact name.
