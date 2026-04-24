// audio_effects.cpp -- Owen Richmond, EECE4632
// hard clip distortion: multiply by gain, smash anything over Q15_MAX flat
// simplified from audio_effects.py 'hard' mode (skipping peak normalization,
// thats annoying to do in hw since you need the whole buffer first)

#include "audio_effects.h"

void distortion_top(sample_t in_samples[NUM_SAMPLES],
                    sample_t out_samples[NUM_SAMPLES],
                    int gain)
{
    // s_axilite: ARM writes gain and the start signal over a simple control bus
    #pragma HLS INTERFACE s_axilite port=return bundle=CTRL
    #pragma HLS INTERFACE s_axilite port=gain   bundle=CTRL

    // m_axi: core reads/writes audio buffers straight from DDR memory
    // offset=slave means the ARM also passes the buffer addresses over AXI-Lite
    #pragma HLS INTERFACE m_axi depth=NUM_SAMPLES port=in_samples  offset=slave bundle=MEM
    #pragma HLS INTERFACE m_axi depth=NUM_SAMPLES port=out_samples offset=slave bundle=MEM

    // pipeline II=1 means one new sample starts every clock cycle, nice
    DISTORTION_LOOP: for (int i = 0; i < NUM_SAMPLES; i++) {
        #pragma HLS PIPELINE II=1

        acc_t driven = (acc_t)in_samples[i] * (acc_t)gain;  // 32 bits so it doesnt clip early

        if      (driven >  Q15_MAX) driven =  Q15_MAX;  // this is the distortion part
        else if (driven <  Q15_MIN) driven =  Q15_MIN;

        out_samples[i] = (sample_t)driven;
    }
}
