# FPGA Musician

Owen Richmond, EECE 4632 Spring 2026.

Real-time audio effects chain (distortion, tremolo, delay) running on the PL of an AUP-ZU3. HLS IP, AXI master for sample data, AXI-Lite for control, Python on the PS for driving it. Two HLS builds of the same math: Build 1 is three back-to-back pipelined loops in one function, Build 2 is the same code broken into sub-functions with the DATAFLOW pragma. Both bit-exact against a Python reference, both measured on the board.

## What's in this repo

- `python/` -- Python reference (`audio_effects.py`, `tone_generator.py`, `fpga_musician.py`). The `_hls` variants in `audio_effects.py` match the hardware arithmetic sample for sample.
- `vitis_hls/build1_pipeline/` -- Build 1 HLS source, testbench, synthesis reports.
- `vitis_hls/build2_dataflow/` -- Build 2 HLS source, testbench, synthesis reports.
- `vitis_hls/Pervious iteration (project update 2)/` -- the original standalone distortion IP, kept for reference.
- `pynq_overlay/` -- bitstreams (`chain.bit`, `chain2.bit`), handoff files, and `run_test.py`, the single test script that runs both builds, measures latency, verifies bit-exactness, and writes WAV output.
- `FINAL REPORT/` -- figures, graph-generation script, test result dumps, and the final report docx.
- `Richmond_Preliminary_Report_Draft.docx` -- preliminary report (submitted April 14, 2026).

## Running the Python reference (no board)

```
pip install numpy matplotlib
python python/fpga_musician.py
```

WAV files land in `output/`. Use `distortion_hls()` (not `distortion()`) if you want something that matches the FPGA exactly. The plain one does a peak-normalization step that the hardware cannot do sample-by-sample.

## Running on the board

Upload the following files into **`/home/xilinx/jupyter_notebooks/Preliminary_Project/`** on the AUP-ZU3 (this exact path is hardcoded in `run_test.py`):

| File | Source in repo |
|------|----------------|
| `chain.bit`, `chain.hwh` (Build 1) | `pynq_overlay/` |
| `chain2.bit`, `chain2.hwh` (Build 2) | `pynq_overlay/` |
| `run_test.py` | `pynq_overlay/` |
| `audio_effects.py` | `python/` |
| `tone_generator.py` | `python/` |
| `test_tone.wav` *(optional — synthetic 440 Hz sine used if absent)* | user-supplied |

Then run `run_test.py` from Jupyter on the board. It loads each bitstream in turn, verifies bit-exact match against the Python reference for one chunk and for ten consecutive chunks, measures median and minimum latency over 300 chunks, attempts DATAFLOW-style pipelining, and dumps a report to `output/test_results.txt`. Both `output_build1_pipeline.wav` and `output_build2_dataflow.wav` are written alongside it.

## Results

Both builds pass the one-chunk bit-exact check. Build 1 median latency is 42.3 us per 480-sample chunk, Build 2 is 33.0 us, against a 10 ms (10,000 us) real-time budget. DATAFLOW improves II from 1,470 cycles to 493 cycles (a 3x throughput speedup in synthesis) but the Python driver cannot restart the IP fast enough to exploit the II, so wall-clock throughput is limited by PS overhead rather than PL throughput. Full numbers are in `FINAL REPORT/test_results (2).txt` and in the final report.

## Previous status (April 14 preliminary report)

Distortion was verified bit-exact on the board. Both chain builds had C simulations passing. Build 1 had synthesized. The remaining work was getting Build 2 synthesized, wiring both through Vivado implementation, and running them on the board. All of that is now done.
