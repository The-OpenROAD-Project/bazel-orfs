# wirebound: what it puts on which metal layer

`wirebound.sv` explains what this design is and why it exists. This file
records what it actually routes, because the design's value depends on a
claim that is only true if measured: that it reaches the top of asap7's
metal stack, where no other design in the tree goes.

`MAX_ROUTING_LAYER = M9` here against the platform's `?= M7`, so M8 and
M9 — the two least resistive layers, roughly 8x below M1 — are reachable
for this design and for nothing else in `flow/designs/asap7`. A layer
with no routed segments contributes nothing to an RC fit, so
`wirebound_write_rc` and `wirebound_correlate_rc` are only worth running
if the demand below is non-zero.

## Measured

Global-route guides on the shipped configuration (GROUPS=32,
`CORE_UTILIZATION=55`, `PLACE_DENSITY=0.60`,
`ROUTING_LAYER_ADJUSTMENT=0.25`), core 62.7 x 62.4 um, 13 277 nets
carrying guides.

| layer | pitch | dir | demand | **% of wires** | **% of metal** | raw | mean guide |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M1 | 0.036 | V | 20 575 um | 12.44% | 18.94% | 18.94% | 0.57 um |
| M2 | 0.036 | H | 52 083 | **31.49%** | **63.93%** | 47.95% | 1.19 |
| M3 | 0.036 | V | 45 106 | **27.27%** | **55.37%** | 41.53% | 2.22 |
| M4 | 0.048 | H | 17 880 | 10.81% | 29.26% | 21.95% | 2.45 |
| M5 | 0.048 | V | 10 914 | 6.60% | 17.86% | 13.40% | 2.08 |
| M6 | 0.064 | H | 3 606 | 2.18% | 7.87% | 5.90% | 0.89 |
| M7 | 0.064 | V | 3 800 | 2.30% | 8.29% | 6.22% | 1.10 |
| **M8** | 0.080 | H | 6 657 | **4.02%** | **18.16%** | 13.62% | **3.06** |
| **M9** | 0.080 | V | 4 781 | **2.89%** | **13.04%** | 9.78% | **8.85** |

**Two denominators, and they answer different questions.** *% of wires*
is the layer's share of the design's total routing demand. *% of metal*
is that demand against the track supply the router is allowed to spend —
the core extent across the layer's routing direction divided by its
pitch, times the extent along it, derated by `ROUTING_LAYER_ADJUSTMENT`
to leave room for pins, power and vias. The *raw* column is the same
ratio before the derate, i.e. against every track the layer physically
has. M1 is outside `MIN_ROUTING_LAYER..MAX_ROUTING_LAYER`, so it carries
only pin-level guides and takes no derate.

The two columns disagree because the upper layers are coarse: M8 and M9
are pitched at 0.080 um against M2's 0.036, so they hold 45% as many
tracks. A given share of the design's wires is a little over twice the
track pressure on M8 that it would be on M2.

## What the numbers say

**M8 and M9 are used, and not marginally.** They carry 6.9% of the
design's wires, and 18.2% and 13.0% of the metal they are permitted to
spend. The claim the RC calibration rests on holds.

**Utilization is not monotonic in height.** Demand share falls steadily
up the stack — M2 and M3 alone carry 59% of the wires — but occupancy
does not: M8 sits at 18.2% of its budget, *above* M6 at 7.9% and M7 at
8.3%. Routing skips the middle of the stack and reappears at the top.

**Mean guide length is why.** It climbs from 1.19 um on M2 to 3.06 um on
M8 and 8.85 um on M9 — the top of the stack carries a small number of
long segments, not a share of the general traffic. That is the
resistance-aware router (`ENABLE_RESISTANCE_AWARE` is 1 for asap7, and
`global_route.tcl` passes `-resistance_aware`) steering critical nets
onto the least resistive metal, which pays only for a net long enough to
repay its via stack. On asap7 that break-even is around 8 um of net: the
round trip M2 to M9 and back costs 0.161 ohm of via resistance against a
saving of 0.0208 ohm/um.

M6 and M7 are the layers with no constituency — too resistive to be
worth a long net's via stack, too coarse to be worth a short one's.

## Reproducing

```sh
bazelisk build //test/pre_route_pessimism:layer_usage
```

It prints the table above as `LAYER_USAGE` lines and writes the same
data as JSON. The probe errors out rather than reporting zeros if no net
carries guides, since every per-layer number would otherwise be
well-formed and meaningless.
