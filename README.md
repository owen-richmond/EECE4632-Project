# FPGA Musician GUIDE

**Update (April 2026):** Build 1 (distortion + tremolo + delay chain, sequential pipelined loops) is synthesized and the Vivado block design is done. chain.bit and chain.hwh are in pynq_overlay alongside the original distortion files. Test scripts are in vitis_hls/ and expect everything to live in a folder called Preliminary_Project on the board. Build 2 (DATAFLOW version) is written and the C sim passes but hasn't been synthesized yet. See IMPLEMENTATION_GUIDE.md for the full setup walkthrough.

---

Owen Richmond, EECE4632

Audio effects processor on the AUP-ZU3. Distortion (hard clip) is working on the FPGA, tremolo and delay are Python only for now.

To run the Python reference: pip install numpy matplotlib, then run fpga_musician.py. WAV files go to output/.

To test on the board: upload everything in pynq_overlay plus pynq_test.py and the python files to Jupyter, run pynq_test.py cell by cell.

Note: use distortion_hls() not distortion() if you're comparing against FPGA output, the regular one does a normalization step the hardware doesn't.

What's implemented so far: hard clip distortion is fully working in HLS, verified with a testbench (3 tests, all pass) and confirmed bit-exact on the board. Synthesis hits II=1 on the main loop which is what we wanted. Tremolo and delay are also done -- two chain builds exist in vitis_hls/build1_pipeline (sequential loops) and vitis_hls/build2_dataflow (DATAFLOW pragma), both with their own testbenches.

The original standalone distortion HLS files are in vitis_hls/Pervious iteration (project update 2)/ for reference. Active development is in build1_pipeline and build2_dataflow. Next step is getting both chain builds through Vivado and verified on the board.
