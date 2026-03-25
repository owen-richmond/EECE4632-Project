// audio_effects.h -- Owen Richmond, EECE4632
// types and constants for the HLS distortion core

#ifndef AUDIO_EFFECTS_H
#define AUDIO_EFFECTS_H

#include "ap_int.h"  // xilinx fixed-width int types

// keep these in sync with python/audio_effects.py
#define SAMPLE_RATE 48000
#define NUM_SAMPLES 480    // 10ms chunk at 48khz
#define Q15_MAX     32767
#define Q15_MIN    -32768

typedef ap_int<16> sample_t;  // one Q1.15 audio sample
typedef ap_int<32> acc_t;     // temp type for multiply so we dont overflow

// gain=1 is clean, gain=4 is crunchy
void distortion_top(sample_t in_samples[NUM_SAMPLES],
                    sample_t out_samples[NUM_SAMPLES],
                    int gain);

#endif
