// audio_effects.cpp -- Owen Richmond, EECE4632
// build 2: DATAFLOW version of the chain
//
// the idea is mine -- wrap each effect in its own sub-function so HLS can
// schedule them as overlapping pipeline stages instead of running strictly
// back to back. in build 1 the three loops run sequentially: dist finishes,
// then tremolo starts, then delay starts. here they can all be "in flight"
// at the same time, processing different samples concurrently.
//
// the refactor into sub-functions was done with Claude -- i knew what i wanted
// architecturally but wasn't going to rewrite all teh loops from scratch just
// to wrap them in functions. the math is exaclty the same as build 1.
//
// what to look for in the synthesis report vs build 1:
//   latency: should be lower here (stages overlap instead of stacking)
//   BRAM:    will be higher here (HLS adds ping-pong buffers for mid1/mid2)
//   II:      about the same per-loop, same math

#include "audio_effects.h"

static const int SIN_LUT64[64] = {
        0,  3211,  6392,  9511, 12539, 15446, 18204, 20787,
    23169, 25329, 27244, 28897, 30272, 31356, 32137, 32609,
    32767, 32609, 32137, 31356, 30272, 28897, 27244, 25329,
    23169, 20787, 18204, 15446, 12539,  9511,  6392,  3211,
        0, -3211, -6392, -9511,-12539,-15446,-18204,-20787,
   -23169,-25329,-27244,-28897,-30272,-31356,-32137,-32609,
   -32767,-32609,-32137,-31356,-30272,-28897,-27244,-25329,
   -23169,-20787,-18204,-15446,-12539, -9511, -6392, -3211
};

static void do_distortion(sample_t in[NUM_SAMPLES], sample_t out[NUM_SAMPLES], int gain)
{
    DIST_LOOP: for (int i = 0; i < NUM_SAMPLES; i++) {
        #pragma HLS PIPELINE II=1
        acc_t d = (acc_t)in[i] * gain;
        if      (d >  Q15_MAX) d =  Q15_MAX;
        else if (d <  Q15_MIN) d =  Q15_MIN;
        out[i] = (sample_t)d;
    }
}

static void do_tremolo(sample_t in[NUM_SAMPLES], sample_t out[NUM_SAMPLES],
                       int rate_step, int depth_q15)
{
    static int phase = 0;
    TREM_LOOP: for (int i = 0; i < NUM_SAMPLES; i++) {
        #pragma HLS PIPELINE II=1
        int lfo_01 = (SIN_LUT64[(phase >> 10) & 0x3F] + Q15_MAX) >> 1;
        acc_t gq   = (Q15_MAX - depth_q15) + ((acc_t)depth_q15 * lfo_01 >> 15);
        acc_t s    = ((acc_t)in[i] * gq) >> 15;
        if      (s >  Q15_MAX) s =  Q15_MAX;
        else if (s <  Q15_MIN) s =  Q15_MIN;
        out[i] = (sample_t)s;
        phase = (phase + rate_step) & 0xFFFF;
    }
}

static void do_delay(sample_t in[NUM_SAMPLES], sample_t out[NUM_SAMPLES],
                     int delay_n, int feedback_q15, int mix_q15)
{
    static sample_t delay_buf[MAX_DELAY_SAMP];
    #pragma HLS RESOURCE variable=delay_buf core=RAM_2P_BRAM
    static int wp = 0;
    int dn = (delay_n < 1) ? 1 : (delay_n >= MAX_DELAY_SAMP ? MAX_DELAY_SAMP-1 : delay_n);

    DELAY_LOOP: for (int i = 0; i < NUM_SAMPLES; i++) {
        #pragma HLS PIPELINE
        #pragma HLS DEPENDENCE variable=delay_buf inter false
        int rp = wp - dn;
        if (rp < 0) rp += MAX_DELAY_SAMP;
        acc_t delayed = delay_buf[rp];
        acc_t dry = ((acc_t)in[i] * (Q15_MAX - mix_q15)) >> 15;
        acc_t wet = (delayed       *            mix_q15)  >> 15;
        acc_t s   = dry + wet;
        if      (s >  Q15_MAX) s =  Q15_MAX;
        else if (s <  Q15_MIN) s =  Q15_MIN;
        out[i] = (sample_t)s;
        acc_t fb = (acc_t)in[i] + (delayed * feedback_q15 >> 15);
        if      (fb >  Q15_MAX) fb =  Q15_MAX;
        else if (fb <  Q15_MIN) fb =  Q15_MIN;
        delay_buf[wp] = (sample_t)fb;
        if (++wp >= MAX_DELAY_SAMP) wp = 0;
    }
}

// DATAFLOW lets HLS run the three sub-functions as overlapping pipeline stages
// mid1 and mid2 become ping-pong BRAMs so do_tremolo can start on chunk N
// while do_distortion is already working on chunk N+1
void chain_top(sample_t in_samples[NUM_SAMPLES],
               sample_t out_samples[NUM_SAMPLES],
               int dist_gain, int trem_rate_step, int trem_depth_q15,
               int delay_n,   int feedback_q15,   int mix_q15)
{
    #pragma HLS INTERFACE s_axilite port=return          bundle=CTRL
    #pragma HLS INTERFACE s_axilite port=dist_gain       bundle=CTRL
    #pragma HLS INTERFACE s_axilite port=trem_rate_step  bundle=CTRL
    #pragma HLS INTERFACE s_axilite port=trem_depth_q15  bundle=CTRL
    #pragma HLS INTERFACE s_axilite port=delay_n         bundle=CTRL
    #pragma HLS INTERFACE s_axilite port=feedback_q15    bundle=CTRL
    #pragma HLS INTERFACE s_axilite port=mix_q15         bundle=CTRL
    #pragma HLS INTERFACE m_axi depth=NUM_SAMPLES port=in_samples  offset=slave bundle=MEM
    #pragma HLS INTERFACE m_axi depth=NUM_SAMPLES port=out_samples offset=slave bundle=MEM
    #pragma HLS DATAFLOW

    sample_t mid1[NUM_SAMPLES], mid2[NUM_SAMPLES];

    do_distortion(in_samples, mid1, dist_gain);
    do_tremolo(mid1, mid2, trem_rate_step, trem_depth_q15);
    do_delay(mid2, out_samples, delay_n, feedback_q15, mix_q15);
}
