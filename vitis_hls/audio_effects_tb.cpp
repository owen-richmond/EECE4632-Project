// audio_effects_tb.cpp -- Owen Richmond, EECE4632
// testbench for distortion_top(), runs as plain C++ in vitis C sim
// returns 0 = pass, nonzero = fail (vitis checks this automatically)

#include "audio_effects.h"
#include <iostream>
#include <math.h>

static void make_sine(sample_t buf[NUM_SAMPLES], float freq, float amp)
{
    for (int i = 0; i < NUM_SAMPLES; i++) {
        float s = sinf(6.28318f * freq * i / SAMPLE_RATE) * amp * Q15_MAX;
        if (s >  Q15_MAX) s =  Q15_MAX;
        if (s < -Q15_MAX) s = -Q15_MAX;
        buf[i] = (sample_t)(int)s;
    }
}

int main()
{
    sample_t in_buf[NUM_SAMPLES], out_buf[NUM_SAMPLES];
    int errors = 0;

    // test 1: quiet signal, gain=1, nothing should clip
    std::cout << "Test 1: no clipping..." << std::endl;
    make_sine(in_buf, 440.0f, 0.3f);
    distortion_top(in_buf, out_buf, 1);
    for (int i = 0; i < NUM_SAMPLES; i++) {
        if (out_buf[i] != in_buf[i]) {
            std::cout << "  FAIL sample " << i << ": " << (int)in_buf[i]
                      << " -> " << (int)out_buf[i] << std::endl;
            errors++;
        }
    }
    std::cout << (errors == 0 ? "  pass" : "  FAILED") << std::endl;

    // test 2: loud signal, gain=4, peak = 29490*4 = 117960 >> 32767, must clip
    std::cout << "Test 2: clipping..." << std::endl;
    make_sine(in_buf, 440.0f, 0.9f);
    distortion_top(in_buf, out_buf, 4);
    int t2err = 0;
    bool clipped = false;
    for (int i = 0; i < NUM_SAMPLES; i++) {
        if (out_buf[i] > Q15_MAX || out_buf[i] < Q15_MIN) { t2err++; }
        if ((int)out_buf[i] == Q15_MAX || (int)out_buf[i] == Q15_MIN) clipped = true;
    }
    if (!clipped) { std::cout << "  WARNING: expected clipping, got none" << std::endl; t2err++; }
    std::cout << (t2err == 0 ? "  pass" : "  FAILED") << std::endl;
    errors += t2err;

    // test 3: silence in = silence out, 0 * anything = 0
    std::cout << "Test 3: zeros..." << std::endl;
    for (int i = 0; i < NUM_SAMPLES; i++) in_buf[i] = 0;
    distortion_top(in_buf, out_buf, 4);
    int t3err = 0;
    for (int i = 0; i < NUM_SAMPLES; i++)
        if ((int)out_buf[i] != 0) t3err++;
    std::cout << (t3err == 0 ? "  pass" : "  FAILED") << std::endl;
    errors += t3err;

    std::cout << (errors == 0 ? "\nAll passed, go synthesize" : "\nFailed, fix it first") << std::endl;
    return errors;
}
