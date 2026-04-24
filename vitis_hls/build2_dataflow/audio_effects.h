// audio_effects.h -- Owen Richmond, EECE4632
// build 2: same interface as build 1, DATAFLOW added inside chain_top
// identical from the outside, different scheduling inside -- thats the point

#ifndef AUDIO_EFFECTS_H
#define AUDIO_EFFECTS_H

#include "ap_int.h"

#define SAMPLE_RATE     48000
#define NUM_SAMPLES     480
#define Q15_MAX         32767
#define Q15_MIN        -32768
#define MAX_DELAY_SAMP  12000

typedef ap_int<16> sample_t;
typedef ap_int<32> acc_t;

void chain_top(sample_t in_samples[NUM_SAMPLES],
               sample_t out_samples[NUM_SAMPLES],
               int dist_gain, int trem_rate_step, int trem_depth_q15,
               int delay_n,   int feedback_q15,   int mix_q15);

#endif
