# FPGA Musician
Owen Richmond, EECE4632

Audio effects processor on the AUP-ZU3. Distortion (hard clip) is working on the FPGA, tremolo and delay are Python only for now.

To run the Python reference: pip install numpy matplotlib, then run fpga_musician.py. WAV files go to output/.

To test on the board: upload everything in pynq_overlay plus pynq_test.py and the python files to Jupyter, run pynq_test.py cell by cell. Board is at 192.168.3.1, password is xilinx.

Note: use distortion_hls() not distortion() if you're comparing against FPGA output, the regular one does a normalization step the hardware doesn't.
