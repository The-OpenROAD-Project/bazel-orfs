# Peek poke less Chisel tests built by Bazel

ChiselSim handles builds and runs tests, which is an inversion of control.

When working with Bazel, it is advantageous to leave building to Bazel so as to take advantage of caching.

## Peek poke less tests

The advantage of peek poke less tests is that they can express parallelism in Chisel, such as when driving a master/slave setup with the Decoupled interface.

The input may be randomized, there could be backpressure on input and the final output has to be checked whenever it is ready. This sort of setup was convenient to code with fork/join() in the now deprecated chiseltest framework.

## Creating a peek poke less test

Create a Chisel test bench module that has one `done` top level output signal to indicate when the test is complete and assert in the case where the test fails.

See BUILD file in this folder and read the test.bzl on how to set up chisel_bench_test().

Run the test:

    bazel test :life_test

Output:

    //chisel:life_test                                              (cached) PASSED in 0.0s

A .vcd file is output in test.outputs:

    $ ls bazel-testlogs/chisel/life_test/test.outputs/
    life_test.vcd
