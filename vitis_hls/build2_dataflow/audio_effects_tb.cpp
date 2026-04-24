// audio_effects_tb.cpp -- Owen Richmond, EECE4632
// testbench for build 2 -- same tests as build 1, same function signature
// just making sure DATAFLOW didn't break the math, the numbers should match

#include "audio_effects.h"
#include <iostream>
#include <math.h>

static void make_sine(sample_t buf[NUM_SAMPLES], float freq, float amp)
{
    for (int i = 0; i < NUM_SAMPLES; i++) {
        float s = sinf(6.28318f * freq * i / SAMPLE_RATE) * amp * Q15_MAX;
        buf[i] = (sample_t)(int)(s >  Q15_MAX ?  Q15_MAX :
                                  s < -Q15_MAX ? -Q15_MAX : s);
    }
}

int main()
{
    sample_t in[NUM_SAMPLES], out[NUM_SAMPLES];
    int errors = 0;

    std::cout << "Test 1: bypass..." << std::endl;
    make_sine(in, 440.0f, 0.4f);
    chain_top(in, out, 1, 0, 0, 2400, 0, 0);
    int t1e = 0;
    for (int i = 0; i < NUM_SAMPLES; i++) if (out[i] != in[i]) t1e++;
    std::cout << (t1e == 0 ? "  pass" : "  FAILED") << " (" << t1e << " mismatches)" << std::endl;
    errors += t1e;

    std::cout << "Test 2: distortion clips at gain=6..." << std::endl;
    make_sine(in, 440.0f, 0.9f);
    chain_top(in, out, 6, 0, 0, 2400, 0, 0);
    bool clipped = false, overflowed = false;
    for (int i = 0; i < NUM_SAMPLES; i++) {
        if ((int)out[i] == Q15_MAX || (int)out[i] == Q15_MIN) clipped = true;
        if ((int)out[i] >  Q15_MAX || (int)out[i] <  Q15_MIN) overflowed = true;
    }
    int t2e = (!clipped || overflowed) ? 1 : 0;
    std::cout << (t2e == 0 ? "  pass" : "  FAILED") << std::endl;
    errors += t2e;

    std::cout << "Test 3: silence through full chain..." << std::endl;
    for (int i = 0; i < NUM_SAMPLES; i++) in[i] = 0;
    chain_top(in, out, 4, 7, 20000, 4800, 13000, 16000);
    int t3e = 0;
    for (int i = 0; i < NUM_SAMPLES; i++) if ((int)out[i] != 0) t3e++;
    std::cout << (t3e == 0 ? "  pass" : "  FAILED") << " (" << t3e << " nonzero)" << std::endl;
    errors += t3e;

    std::cout << "Test 4: two chunks, no overflow..." << std::endl;
    bool ok = true;
    for (int chunk = 0; chunk < 2; chunk++) {
        make_sine(in, 440.0f, 0.8f);
        chain_top(in, out, 3, 7, 20000, 4800, 13000, 16000);
        for (int i = 0; i < NUM_SAMPLES; i++)
            if ((int)out[i] > Q15_MAX || (int)out[i] < Q15_MIN) { ok = false; break; }
    }
    std::cout << (ok ? "  pass" : "  FAILED (overflow)") << std::endl;
    if (!ok) errors++;

    std::cout << (errors == 0 ? "\nAll passed, go synthesize" : "\nFailed, fix it first") << std::endl;
    return errors;
}
