# Systematic cc_library Extraction for Fast Unit Tests

## Problem

OpenROAD cc_test targets depend on monolithic module libraries (e.g.
`//src/mpl`, `//src/drt`). Changing one line in a unit test triggers
an 8-minute rebuild of the entire module and its transitive deps. The
`features = ["-layering_check"]` workaround in BUILD files is a smell
— it means the test includes private headers and the dep graph is wrong.

## Idea

Extract testable classes from monolithic modules into focused cc_library
targets with minimal deps (typically just odb + utl). Point cc_test
targets at these instead of the whole module.

Proven with mpl:snapper — unit test compiles in 5 seconds instead of
8 minutes. The pattern follows hzeller's efc23530ac (cyclic dep
workaround for rsz/grt) generalized across all modules.

Candidates (every cc_test with `features = ["-layering_check"]`):

| Module | Tests | What to extract |
|--------|-------|-----------------|
| dst | dst_balancer_test, dst_worker_test | Balancer, Worker |
| drt | gc_unittest | GC checker |
| dft | 4 scan architect tests | ScanArchitect |
| gpl | gpl_fft_unittest | FFT solver |
| cts | cts_unittest | CTS core |
| rmp | 2 ABC tests | ABC interface |
| web | 4 tests (clock_tree_report, request_handler, tile_generator, snap) | Web handlers |
| mpl | mpl_snapper_unittest (done) | Snapper |

## Impact

Every OpenROAD developer iterating on unit tests. 5-second compile
instead of 8-minute. Compounds across CI — each test run that doesn't
rebuild the world saves machine-minutes. Also enforces proper
dependency hygiene as a side effect.

## Effort

Medium per module (extract class, add cc_library, update BUILD, qualify
namespace references). Could be done incrementally — one module per PR.
Good candidate for nerd-sniping hzeller via a feature request on one
of his BUILD-related PRs.
