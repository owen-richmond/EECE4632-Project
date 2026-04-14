// audio_effects.cpp -- Owen Richmond, EECE4632
// build 1: distortion -> tremolo -> delay, all in one function, three loops
// each loop pipelined at II=1, stages run sequentially (check synthesis report
// and compare form build 2 -- thats the whole point of having two builds)
//
// i kept the same interface pattern as the working distortion build so the
// vivado block design setup is basically the same, just with more AXI params

#include "audio_effects.h"

// 64-entry Q1.15 sine LUT for the tremolo LFO
// one full period, index selected by top 6 bits of a 16-bit phase counter
// Claude generated these values because I wasn't going to type 64 sines by hand
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

    sample_t mid1[NUM_SAMPLES];  // distortion output
    sample_t mid2[NUM_SAMPLES];  // tremolo output

    // --- stage 1: distortion ---
    // exact same logic as the original working build
    DIST_LOOP: for (int i = 0; i < NUM_SAMPLES; i++) {
        #pragma HLS PIPELINE II=1
        acc_t d = (acc_t)in_samples[i] * dist_gain;
        if      (d >  Q15_MAX) d =  Q15_MAX;
        else if (d <  Q15_MIN) d =  Q15_MIN;
        mid1[i] = (sample_t)d;
    }

    // --- stage 2: tremolo ---
    // static phase counter rolls forward between 10ms chunks so the LFO
    // stays continuous across calls instead of restarting every time
    static int phase = 0;
    TREM_LOOP: for (int i = 0; i < NUM_SAMPLES; i++) {
        #pragma HLS PIPELINE II=1
        int lfo_01 = (SIN_LUT64[(phase >> 10) & 0x3F] + Q15_MAX) >> 1;
        acc_t gq   = (Q15_MAX - trem_depth_q15) + ((acc_t)trem_depth_q15 * lfo_01 >> 15);
        acc_t s    = ((acc_t)mid1[i] * gq) >> 15;
        if      (s >  Q15_MAX) s =  Q15_MAX;
        else if (s <  Q15_MIN) s =  Q15_MIN;
        mid2[i] = (sample_t)s;
        phase = (phase + trem_rate_step) & 0xFFFF;
    }

    // --- stage 3: delay ---
    // circular buffer in BRAM, persists between calls so the echo tail sticks around
    // II may come out as 1 or 2 depending on how HLS handles the BRAM read-then-write
    // interesting to compare against build 2 -- note the II in the synthesis report
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
        acc_t dry = ((acc_t)mid2[i] * (Q15_MAX - mix_q15)) >> 15;
        acc_t wet = (delayed        *            mix_q15)   >> 15;
        acc_t s   = dry + wet;
        if      (s >  Q15_MAX) s =  Q15_MAX;
        else if (s <  Q15_MIN) s =  Q15_MIN;
        out_samples[i] = (sample_t)s;
        acc_t fb = (acc_t)mid2[i] + (delayed * feedback_q15 >> 15);
        if      (fb >  Q15_MAX) fb =  Q15_MAX;
        else if (fb <  Q15_MIN) fb =  Q15_MIN;
        delay_buf[wp] = (sample_t)fb;
        if (++wp >= MAX_DELAY_SAMP) wp = 0;
    }
}
