# EXPERIMENTAL - najaeda post-synthesis cleanup example

dirty.v has various issues after synthesis that we'd like to clean up with najaeda.

## Synthesis

Run:

    bazelisk build //naja:dirty_synth

Outputs:

    Target //naja:dirty_synth up-to-date:
    [deleted]
      bazel-bin/naja/results/asap7/dirty/base/1_2_yosys.v    
    [deleted]

We see that we have unused inputs that are not cleaned up:

    $ grep unused bazel-bin/naja/results/asap7/dirty/base/1_2_yosys.v
        .unused_data({ _09_, _09_, _09_, _09_, _09_, _09_, _09_, _09_ }),

## Cleaning

To clean netlist:

    bazelisk build //naja:cleaned_synth

This outputs:

    [deleted]
    Target //naja:cleaned_synth up-to-date:
      bazel-bin/naja/cleaned.v
    [deleted]

We expect all unused inputs/outputs to be cleaned up:

    $ grep unused bazel-bin/naja/cleaned.v
    # Expected: no output; all unused inputs/outputs have been removed
