# FPGA Musician GUIDE
Owen Richmond, EECE4632

Audio effects processor on the AUP-ZU3. Distortion (hard clip) is working on the FPGA, tremolo and delay are Python only for now.

To run the Python reference: pip install numpy matplotlib, then run fpga_musician.py. WAV files go to output/.

To test on the board: upload everything in pynq_overlay plus pynq_test.py and the python files to Jupyter, run pynq_test.py cell by cell.

Note: use distortion_hls() not distortion() if you're comparing against FPGA output, the regular one does a normalization step the hardware doesn't.

What's implemented so far: hard clip distortion is fully working in HLS, verified with a testbench (3 tests, all pass) and confirmed bit-exact on the board. Synthesis hits II=1 on the main loop which is what we wanted. Tremolo and delay are done in Python and will be ported to HLS next.

Plan for the rest of the semester is to port tremolo and delay into HLS and chain them together as a pipeline, then wire everything up in a Vivado block design so all three effects run on the FPGA. Stretch goal is hooking up a real audio codec for live input/output but that might be ambitious.
