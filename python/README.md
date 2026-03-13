# FPGA Musician - Python Reference

Python side of my EECE4632 FPGA audio effects project. Generates MIDI messages, synthesizes tones at 48kHz, and runs them through tremolo, distortion, and delay. The outputs are the "golden reference" I'll compare against once the FPGA implementation is working.

## How to run

```bash
pip install numpy matplotlib
python fpga_musician.py
```
THATS IT!!! 

WAV files and plots go into `output/`. Open them in Audacity to listen. Or anything that plays MP3

or just do it in VScode, works on my machine lol. Gitgore for __pychache__ and output, gets annoying to have those bouncing around

Thx

-Owen
