# Pre-route pessimism, and what ORFS timing policy has been fitted to

This directory holds the method and the reproduction commands. The
findings live in the pull request body, generated from the checked-in
result JSONs — a table typed by hand rots the first time a campaign is
re-run.

## The question

ORFS flow policy treats `min_period = clk_period - WNS` as roughly
comparable from stage to stage. Every repair budget downstream of global
placement is set against a pre-route reading of it: `repair_timing`'s
`-repair_tns` share, `SETUP_SLACK_MARGIN`, `SETUP_MOVE_SEQUENCE`, and
where each of those is allowed to act.

Three questions follow, and the third turned out to govern the other two.

1. **How far apart are the pre-route and routed readings?**
2. **Which of ORFS's timing defaults are PDK properties rather than flow
   properties?** asap7 and sky130hd are not the same problem and are
   governed by one set of defaults.
3. **Can any of it be resolved against the flow's own noise?** A knob
   whose effect is smaller than the spread of an ensemble has not been
   shown to do anything, and crediting QoR to it is correlation read as
   causation.

## What was measured

### The gap is real, and it is the opposite sign from the premise

On a design contended enough that a routing layer exceeds the tracks the
router may spend, `min_period` at placement reads **12.0% lower** than at
global route -- placement is optimistic, not pessimistic. With room to
route, the two agree to within 3%: global route takes the direct path and
confirms what placement already said, so **contention is the necessary
ingredient** for the two stages to disagree at all.

### Global route is the noisy number, not the estimate

Over twelve `GPL_RANDOM_SEED` values with everything else fixed:

| | mean | 2 sigma | range |
| --- | --- | --- | --- |
| `min_period` at place | 302.95 ps | 13.2 ps (4.3%) | 291.6 - 315.9 |
| `min_period` at grt | 345.46 ps | 47.5 ps (13.8%) | 317.6 - 387.3 |
| place-to-grt gap | -12.0% | 10.3 points | -6.2% ... -20.1% |

The routed number is **3.6x noisier** than the pre-route estimate that
everything downstream distrusts. That inverts how the flow treats them.

### Which means most single-run comparisons on this design say nothing

The resolvable difference at `k` runs per arm is `2 sigma sqrt(2/k)`. At
one run per arm that is **14.6 points** of place-to-grt gap; at twelve it
is 4.2. A four-arm sweep varying `set_wire_rc` across a 3.5x resistance
range produced arms spanning 12.5 points -- inside the single-run
resolution -- so the honest verdict is **"did not resolve"**, not "no
effect". Reporting it as an effect would have been this study's own
version of the error it set out to document.

## Where the pre-route wire model comes from

Chesterton's Fence: the numbers are not arbitrary, and the fence is
documented. `docs/tutorials/SetRC.md` describes fitting them by
regressing routed segment parasitics against extracted ones, via the
`write_rc` and `correlate_rc` make targets, and states the purpose in
terms of exactly this study's subject -- *"Inaccurate unit RC values can
lead to inconsistent timing results between global route and detailed
route."*

Two structural properties of that procedure matter more than any value it
produces.

**It is gated behind the most expensive part of the flow.** `write_rc`
loads `6_final.odb`, reads the RCX SPEF, and runs a second extraction
with merging disabled. So the wire model that steers timing-driven global
placement can only be calibrated *after* detailed route -- a loop no
large design closes in practice. Whoever cannot afford it inherits
somebody else's fit.

**A layer with no routed segments is skipped, not estimated.**
`fit_layer_models` drops any layer absent from the segment data, so it
gets no fitted row *and contributes nothing to the `set_wire_rc` blend*,
which is a length-weighted mean over the layers that appear. Since every
asap7 design but `aes-block` caps signal routing at M7, and power nets
are excluded from the fit, a blend fitted over the asap7 population has
**no M8 or M9 weight at all** -- while the shipped file carries M8/M9
rows. A design routing on those layers inherits a constant that has never
seen them.

So the finding is not that ORFS's numbers are wrong. ORFS has the method,
the tooling, a per-platform target and a tutorial. What is missing is
plumbing, and half of that gap closed while this study was being run.

bazel-orfs now carries `SET_RC_TCL` as a per-design RC file (patches
0050-0055), read in `load.tcl`, `open.tcl` and `detail_place.tcl` -- the
last of which read neither and dropped any override during `3_5`. So the
*destination* for a per-design fit exists today, which it did not when
this study started.

What is still missing is the path into it: nothing in the flow refits for
your design, nothing records which designs the shipped default was fitted
from, and `correlate_rc` prints Tcl to stdout for a human to paste. The
fit and the file it belongs in are both there; they are not connected.

Regenerating the inventory across that change leaves it byte-identical --
the patches alter how `SET_RC_TCL` is *read*, not asap7's
`MAX_ROUTING_LAYER`, its `setRC.tcl` values, or any `repair_timing` call
site -- so every measured claim above survives the bump. Only this
paragraph needed correcting, which is the point of deriving the rest.

## Why a new design was needed

ORFS's asap7 designs do not enter this regime, and the inventory says so
rather than asserting it — see `//test/pre_route_pessimism:inventory_json`,
which derives the table from ORFS's own `config.mk` files, `setRC.tcl`,
`variables.yaml` and stage scripts at the pinned commit.

`flow/designs/asap7/wirebound/` is the design added for it: an all-to-all
register mixing network whose fan-in sets are scattered by construction,
so the inter-group nets stay die-crossing however the placer folds the
design, with a balanced XOR reduction so logic depth stays at four levels
and the period is a wire measurement rather than a gate measurement. It
carries no macros, no SRAM, no second clock domain and no hierarchy: each
of those would confound the thing being measured, and each is already
represented elsewhere in ORFS.

Its purpose is narrower and more useful than "shows the effect": it is
the design on which the RC calibration loop is **cheap enough to close**.
Reaching a fitted wire model needs detailed route and two extractions,
which the designs that care about it cannot afford; `wirebound` gets
there in minutes while being the only asap7 design that puts signal and
clock nets on M8/M9.

It is shaped to be **upstreamable**, in ORFS's own design layout, because
the protection worth having is ORFS CI defending this regime against
regressions.

## The instrument, and the trap it avoids

A stage's timing means nothing without the parasitics and clock treatment
ORFS chose for that stage. `flow/scripts/open.tcl`'s `read_timing` is the
only place that choice is written down:

| design stage | parasitics | propagated clock |
| --- | --- | --- |
| 1 synth, 2 floorplan | `set_wire_rc` only, no estimate | no |
| 3 place | `estimate_parasitics -placement` | no |
| 4 cts | `estimate_parasitics -placement` | yes |
| 5 grt, route | `estimate_parasitics -global_routing` | yes |
| 6 final | `read_spef` | yes |

`stage_ladder.tcl` therefore sources `open.tcl` and calls `read_timing`
rather than reimplementing it, and each rung records the branch it got.
Reimplementing this is how a ladder ends up comparing a stage against
itself under different rules and reporting the difference as a stage
effect.

`min_period` is sampled through `//test/estimation_ladder:extract_lib.tcl`,
reused rather than copied: it is deliberately the one copy of the sampling
logic, and a second study measuring `min_period` its own way would not be
comparable with the first.

## Assertions that gate the results

In this harness the default failure mode is quiet wrong data, not a
crash. Each of these produces a loud failure instead of a plausible
number:

- **The design is in the regime.** `layer_usage.tcl` reads per-layer
  routing demand from the global-route guides and errors out if no net
  carries guides at all — otherwise every per-layer figure would be a
  well-formed zero. Setting `MAX_ROUTING_LAYER = M9` permits the top of
  the stack; it does not mean a net went there.
- **The top of the stack is scarce, not idle.** Demand is reported
  against track supply derived from each layer's pitch, because asap7's
  upper layers are coarse and a congested design can want M8/M9 and
  still not be able to have much of it.
- **The baseline has something to repair.** A design that closes reports
  zero deltas for every repair knob, indistinguishable from a null
  result.

## Reproducing

**No results are checked in.** They are the output of a campaign, not tree
content, so the generators discover whatever a re-run has produced under
`results/` and every section reports when its inputs are absent -- which is
what keeps a partial study from reading as a complete one. The findings live
in the pull request that produced them.

What it costs, measured on a 32-core box:

| axis | target | leaves | wall time |
| --- | --- | --- | --- |
| inventory | `:inventory_update` | none | seconds, no flow at all |
| size curve | `:sizes_update` | 2 collected (2 more declared) | ~20 min |
| shape | `:shapes_update` | 6, sharing one synthesis | ~10 min |
| wire RC | `:rc_update` | 4 | ~10 min |
| seeds | `:seeds_update` | 12 | ~10 min |
| policy | `:policy_update` | 36 + 36 probes | ~15 min |
| RC fit | `:rc_fit` | needs `final` + RCX | ~6 min |

Roughly forty minutes for the full set, dominated by the arms that need
repair to actually run. `SKIP_LAST_GASP=1` on the design is part of why that
is affordable: last gasp is the long tail of `repair_timing` and there is no
reason to expect a `min_period` cliff in it.

Then `:report` and `:plots` regenerate the write-up and the figures from
whatever landed.

## The old reproduction notes

The inventory needs no flow run:

```sh
bazelisk build //test/pre_route_pessimism:inventory_json
```

The size curve the design's dimensions were picked off, one variant per
point:

```sh
bazelisk build //test/pre_route_pessimism:wirebound_size_g64_grt
```

The regime assertion and the `min_period` ladder:

```sh
bazelisk build //test/pre_route_pessimism:layer_usage
bazelisk build //test/pre_route_pessimism:ladder_place \
               //test/pre_route_pessimism:ladder_cts \
               //test/pre_route_pessimism:ladder_grt
```

## What this does not show

The premise this study started from -- that placement reads *pessimistic*
against global route by tens of percent -- is not reproduced here.
Measured on a public design with the stock platform RC, placement reads
optimistic by 12%. A pessimistic pre-route reading is reachable by
raising the `set_wire_rc` constant, but that is a choice about an input,
not a property of the flow, and this study does not claim a value for it.

No knob is shown to help or hurt. The seed ensemble establishes what
would be needed to show it -- twelve runs per arm to resolve four points
of gap -- and the arms run so far are single runs.

## Limits

Stated here so they are not discovered later. One synthetic design, one
PDK, OpenROAD at one commit. Global route is used as the reference rung
while being itself optimistic against signoff extraction, so it must not
be quietly promoted to truth. The perturbation arms measure the spread of
the instrument, not the spread of the flow re-run end to end, so they
bound reproducibility rather than the accuracy any predictor could reach.
