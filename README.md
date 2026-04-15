# FPGA Musician GUIDE

**Update (April 2026) -- chain build is working on hardware.** To run it: upload everything in pynq_overlay/ (except the old/ folder and the .py files that aren't test scripts) into a folder called Preliminary_Project on the board, create a Preliminary_Project/output/ folder, then run pynq_test_chain.py cell by cell in Jupyter. Files you need: chain.bit, chain.hwh, audio_effects.py, tone_generator.py, pynq_test_chain.py. Ignore old/ (that's just the distortion-only bitstream for reference).

---

Owen Richmond, EECE4632

Audio effects processor on the AUP-ZU3. Distortion (hard clip) is working on the FPGA, tremolo and delay are Python only for now.

To run the Python reference: pip install numpy matplotlib, then run fpga_musician.py. WAV files go to output/.

To test on the board: upload everything in pynq_overlay plus pynq_test.py and the python files to Jupyter, run pynq_test.py cell by cell.

Note: use distortion_hls() not distortion() if you're comparing against FPGA output, the regular one does a normalization step the hardware doesn't.

What's implemented so far: hard clip distortion is fully working in HLS, verified with a testbench (3 tests, all pass) and confirmed bit-exact on the board. Synthesis hits II=1 on the main loop which is what we wanted. Tremolo and delay are also done -- two chain builds exist in vitis_hls/build1_pipeline (sequential loops) and vitis_hls/build2_dataflow (DATAFLOW pragma), both with their own testbenches.

The original standalone distortion HLS files are in vitis_hls/Pervious iteration (project update 2)/ for reference. Active development is in build1_pipeline and build2_dataflow. Next step is getting both chain builds through Vivado and verified on the board.
