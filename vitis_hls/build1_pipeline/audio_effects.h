// audio_effects.h -- Owen Richmond, EECE4632
// build 1: single chain_top, three sequential pipelined loops
// same interface pattern as the working distortion build

#ifndef AUDIO_EFFECTS_H
#define AUDIO_EFFECTS_H

#include "ap_int.h"

#define SAMPLE_RATE     48000
#define NUM_SAMPLES     480      // 10ms at 48kHz
#define Q15_MAX         32767
#define Q15_MIN        -32768
#define MAX_DELAY_SAMP  12000   // 250ms max, 24KB of BRAM

typedef ap_int<16> sample_t;
typedef ap_int<32> acc_t;

// dist_gain: 1=clean 4=crunchy | trem_rate_step: int(rate_hz*65536/48000)
// trem_depth_q15: 0..32767 | delay_n: samples | feedback/mix: Q15
void chain_top(sample_t in_samples[NUM_SAMPLES],
               sample_t out_samples[NUM_SAMPLES],
               int dist_gain, int trem_rate_step, int trem_depth_q15,
               int delay_n,   int feedback_q15,   int mix_q15);

#endif
