# Memory-level parallelism: are OpenROAD's hot loops written for a wide machine?

Written down so another machine can pick it up: what the source audit
establishes, what the literature already settles (including what it costs
this idea), the improvement that does not require changing OpenSTA, and the
campaign that would prove or kill it.

The source audit needs no particular machine and is complete below. The
measurement campaign does, and "Campaign" states what it must provide; nothing
here assumes the host that did the reading.

## The model: what actually limits misses in flight

Little's law: misses in flight = miss latency x miss issue rate. At ~300 cycles
to DRAM, 128 outstanding misses needs one issued every ~2.3 cycles; at one miss
per ~16 instructions that implies a ~2048-entry instruction window.

**The discriminator is not chain depth.** A loop iterating an *array of* `a`s,
each chasing `a[i] -> b -> c -> d`, has a 4-deep chain per iteration, but the
chain *heads* are index-computable, the array walk is a hardware-prefetchable
stream, and each chain holds only one outstanding miss at a time. So K
iterations resident in the window overlap K chains:

    MLP = min(K, MSHRs),  K = window size / instructions per iteration

Depth sets each chain's own latency; it does not cap the parallelism. Loops
sort into two classes, and the remedy differs completely:

- **Index-computable head** — `a[i]`, stride known. MLP scales with the window.
  The limiters are instructions per iteration and anything that flushes the
  window.
- **Load-derived head** — the next iteration's address is a field of this
  iteration's loaded data (linked-list walk; a priority-queue pop whose next
  index comes out of the popped element). MLP = 1 at any window width. Only an
  algorithmic or layout change helps.

Three consequences worth stating up front, because they shape the measurements:

**Which resource binds.** A prefetch has no architectural destination: it
allocates a fill buffer but no physical register and no load-queue entry, and
retires without waiting on the fill. It decouples *initiating* a miss from
*holding* the result, and its only cost is instructions per iteration — which is
what sets K. Loop inversion (gather N heads, then N second hops) cannot keep the
batch in registers, because x86-64 has 16 architectural GPRs; the batch lands in
a scratch array, each value stores shortly after arrival, and the register file
is not the binding constraint. Register pressure hurts only second-order, via
spill traffic inflating instructions per iteration.

The resources bind in a consistent order on out-of-order x86 cores generally:
**line fill buffers (MSHRs) first — low tens — then the L2 superqueue, then the
load queue (dozens), then the physical register file and the reorder buffer
(hundreds).** The fill buffers bind first by a wide margin, and they are also
the resource that has scaled *least* across generations. That is why "128 misses
in flight" is an aspiration rather than a setting: it asks for more outstanding
*lines* than any shipping part tracks, which is the strongest argument for
raising useful bytes per line rather than chasing outstanding-miss count.

**An MSHR covers a line, not a load.** Loads to the same 64-byte line coalesce
into one fill buffer. An SoA layout where 16 consecutive elements share a line
gets 16 loads per MSHR; ~96-byte records cross-linked by pointers get about one.
That multiplies effective MLP per scarce MSHR, independent of total footprint.
Every loop below is therefore scored on **useful bytes consumed per 64-byte line
touched**, not on element size.

**Division of labour with the prefetcher.** The stride prefetcher covers the
`a[i]` walk for free within a 4 KB page and cannot follow `->b`, `->c`, `->d`.
In a 4-deep chain the hardware already handles the one access that did not need
help. An aggregate outstanding-requests count is therefore uninterpretable;
demand traffic has to be separated from prefetch traffic.

## What the literature already settles

**Chou, Fahs & Abraham, ISCA 2004 — the canonical limiter list.** Using an epoch
model they identify four window-termination conditions: issue-window/ROB size,
serializing instructions, instruction fetch misses, and **unresolvable branch
mispredictions** — a mispredicted branch *dependent on a missing load*, which
cannot resolve until that miss returns and so ends the epoch. That is
OpenROAD's exact signature; see the branch columns below. They also measure
out-of-order issue buying only **12-30% MLP over in-order**, with runahead worth
82% — the window alone is not the lever.

**Ainsworth & Jones, TOCS 2019 — the calibration, and the caution.** Automatic
software prefetch for exactly the `a[i] -> b[...]` pattern wins **1.2-1.35x on
out-of-order cores** (Haswell, Kaby Lake, Knights Landing) against **2.1-2.7x
in-order** — the out-of-order win is small precisely because the window already
extracts the MLP. They state the tradeoff directly: *"there is a tradeoff
between extracting memory-level parallelism through prefetching, and through the
reorder buffer, as extra prefetching code reduces the number of concurrent loop
iterations."* Nested prefetch cost grows **O(n^2) in indirection depth**, because
each level repeats all preceding loads — a hard bound on prefetching OpenROAD's
depth-4/5 chains. And, decisively for how this campaign is scored: *"the
traditional concepts of memory-bound vs compute-bound do not clearly apply for
out-of-order processors ... the workloads are simultaneously compute and memory
bound."* A stall-fraction gate is not a valid scope test here.

**STA-specific — GPU-accelerated STA (ICCAD 2020) and IncreGPUSTA (ICCAD 2025).**
- Full timing: *"Large designs typically have hundreds of levels with enough
  parallelism for running thousands of independent tasks within a level."*
- Incremental: cones range from *"a small local region"* to *"the entire timing
  landscape"*, and the state of the art switches strategy on cone width.
- netcard (million-gate): **max fan-in 8, max fan-out 260.** So repairing the
  linked-list fanin walk buys at most ~8-wide breadth. Parallelism has to come
  from level width, not fanin breadth — this bounds one candidate remedy.
- IncreGPUSTA replaces linked adjacency with a **dual-CSR** representation, i.e.
  the same load-derived to index-computable conversion proposed here, built as a
  shadow and synced back.
- *"the computational overhead of identifying affected cones may exceed the
  benefits of selective propagation."*
- *"optimization algorithms can call a timer millions or even billions of
  times."*

## Established mechanics

All OpenROAD pointers are read at the commit this repo pins in `MODULE.bazel`
(`c7e5e751`), whose `src/sta` gitlink is exactly the OpenSTA SHA `MODULE.bazel`
downloads (`65bd9df5`) — the two pins are consistent. OpenSTA pointers are read
at that SHA.

### The repo-wide facts

Across the whole of `src/` at the pinned commit:

| probe | count |
| --- | --- |
| `__builtin_prefetch` | 0 |
| `_mm_prefetch` | 0 |
| `#pragma omp simd` | 0 |
| `immintrin` | 0 |

`#pragma omp` by tool: `drt` 47, `gpl` 31, `grt` 6, and **`rsz` 0, `est` 0,
`dpl` 0, `cts` 0**.

Neither OpenROAD's `.bazelrc` nor `OPENROAD_COPTS` (`BUILD.bazel:126`) sets
`-march=` or `-mtune=`, so codegen is baseline x86-64: no AVX2, no FMA, and no
vector gather — the one instruction that turns an indexed load scatter into
parallel misses is not available to the compiler. The binary is otherwise
optimized (`opt`, `-O2`); note this is *not* OpenROAD's own `--config=opt`
(`-O3` + full LTO), which this repo does not select.

So OpenROAD contains no explicit memory-parallelism machinery of any kind. It
does not follow that MLP is low — the index-computable loops may get it from the
hardware for free. That is what the campaign must measure.

### OpenSTA is the cross-cutting cost, not one tool among four

`docs/performance.md` ranks the flow's cost knobs. Of the three rated **Very
high**, all three exist to switch off an STA-driven repair loop:

| knob | stage | what it disables | impact |
| --- | --- | --- | --- |
| `REMOVE_ABC_BUFFERS` | floorplan | `repair_timing_helper` — "can run for hours" | Very high |
| `SKIP_CTS_REPAIR_TIMING` | cts | iterative buffer insertion, sizing, cloning, VT swap | Very high |
| `SKIP_INCREMENTAL_REPAIR` | grt | two rounds of `repair_design` + `repair_timing` | Very high |
| `GPL_TIMING_DRIVEN` | place | timing path analysis inside placement iterations | High |
| `SKIP_REPORT_METRICS` | all | `report_checks` / `report_wns` / `report_tns` / ... | Moderate |

The only knob above **Low** that is not STA is `GPL_ROUTABILITY_DRIVEN`. Every
expensive setting this repo documents, bar one, exists to turn OpenSTA off — and
OpenSTA carries the worst structural profile of the four subsystems.

### Loop classification

**Load-derived heads — MLP 1 at any window width:**

| loop | the line that makes it load-derived |
| --- | --- |
| grt 2-D maze pop, `grt/src/fastroute/src/maze.cpp:1439,1481` | `int ind1 = (src_heap[0] - &d1[0][0]);` |
| grt heap sift, `maze.cpp:419-470` | compares `*(array[l])` — 2 dependent loads per level, ~log N levels |
| grt 3-D maze pop, `maze3D.cpp:856+` | same shape, plus **four** integer div/mod on the critical path |
| grt backtrace, `maze.cpp:1492-1519` | `curX = parent_x3_[tmpY][tmpX]` — textbook linked list |
| grt commit walk, `route.cpp:1030-1055` | a `std::set` insert **per traversed tile** |
| drt A\* main loop, `drt/src/dr/FlexGridGraph_maze.cpp:789-814` | `wavefront_.top()` fields feed `getIdx` |
| **OpenSTA fanin/fanout**, `graph/Graph.cc:1594-1600` | `next_ = graph_->edge(next_->vertex_out_next_);` |
| OpenSTA invalid set, `search/Search.cc:1485-1490` | `for (Vertex *vertex : invalid_arrivals_)` over a `std::set` |
| est `updateParasitics`, `est/src/EstimateParasitics.cpp:511,564` | `unordered_set` node chain |

The grt 2-D pop deserves emphasis: between the loaded heap pointer and every
downstream address sits an integer **division and modulo by a runtime
`x_range_`** (`maze.cpp:1447-1448`) — a 20-40 cycle non-pipelined operation on
the critical path of an already-serial chain.

**Index-computable heads — the lever:** essentially all of `gpl`; drt's
6-direction expansion (`FlexGridGraph_maze.cpp:204-216`, but the trip count is
fixed at 6, so MLP caps at 6) and its DRC cost stamping (`FlexDR_maze.cpp:365`,
`:800`, `:921`); grt's monotonic sweeps (`route.cpp:953-971`) and region init;
rsz `repairPath`/`rankPathDrivers` (`policy/SetupLegacyBase.cc:403-419`) and the
hold pass; and **OpenSTA's per-level vertex queue** (`include/sta/Bfs.hh:44-45`,
`using LevelQueue = std::vector<VertexSeq>`), whose levels are independent by
construction.

### Line occupancy, and an instructive inversion

| structure | useful bytes per 64-byte line |
| --- | --- |
| gpl HPWL and density-center scatter — `cx_,cy_` of an 80-byte `GPin` | **8** |
| gpl WA gradient — 4 of 8 WA floats of a 112-byte `GNet` | **~8** |
| gpl `Bin` (88 B) in the density scatter | ~13 |
| grt `parent_x1_/y1_/x3_/y3_` — four separate `int16_t` arrays | **~2** |
| grt `hv_`/`hyper_*` — `bool` arrays, on a y-step | **1** |
| drt DRC stamping on a horizontal layer | 16 |
| OpenSTA arrival pass over 48-byte `Path` records | ~11 |
| gpl `FloatPoint` coordinate arrays; gpl FFT row/PDE pass | **64** |
| drt `Node` (16 B, planar neighbours); drt DRC stamping on a vertical layer | **64** |

The inversion is worth naming: **gpl is hurt by AoS, grt by over-split SoA.**
gpl packs 80-112 byte records and reads 8 bytes of them; grt splits four
`int16_t` parent arrays that are always read together and pays four line fills
for eight bytes. Neither is "use SoA" — the rule is that fields read together
should share a line and fields read apart should not.

drt's DRC stamping is a third case: `getIdx` transposes the fast axis per layer
(so the preferred routing direction is unit-stride), but the stamping loop nest
is fixed `i` outer / `j` inner. The same loop therefore gets 64/64 on vertical
layers and 16/64 on horizontal ones.

### Working sets decide who is even in scope

- **grt** forces `x_range_ = max(1000, max(x_grid_, y_grid_))`
  (`fastroute/src/FastRoute.cpp:303-305`), so `d1_2D_`+`d2_2D_` are ≥16 MB
  before the design says anything; `Graph2D`'s 24-byte `Edge` arrays run 48-432
  MB, and the 3-D maze state exceeds 300 MB. Decisively DRAM.
- **OpenSTA** at 1 M vertices ≈ 850 MB, of which the arrival `Path` plane alone
  is ~384 MB, spread over ~2N+E individual `new[]` allocations. Decisively DRAM.
- **gpl** scales to hundreds of MB in `GCell`/`GPin`/`GNet`, but its bin array is
  ~23 MB at 512x512 — straddling typical LLC capacity, so whether gpl's density
  loops are a DRAM problem is a property of the host and must be reported
  against its measured LLC size, not assumed — and its FFT grids ~4 MB.
- **drt's per-worker grid graph is ~2-3 MB** — the 7x7-GCell clip
  (`TritonRoute.cpp:1185`) keeps it in L2/L3 *by design*. **drt is not a DRAM
  problem**; it is a dependence and mispredict problem. It is the positive
  counterexample in this document, not a target.

### The incremental regime, and why it may be the whole story

`repair_setup` repairs endpoints strictly one at a time
(`policy/SetupLegacyPolicy.cc:353`, per-endpoint) and, inside the per-pass loop
(`:141`), performs a full parasitics update and a full incremental timing update
before reading the next slack:

```cpp
// policy/SetupLegacyPolicy.cc:236-238
    estimate_parasitics_->updateParasitics();
    sta_->findRequireds();
    refreshEndpointSlacks(endpoint_state);
```

`repair_hold`, in the same codebase, does not. `repairHoldPass` calls
`updateParasitics()` **once** (`RepairHold.cc:503`) and then repairs *every*
failing endpoint (`:507`), with `findRequireds()` hoisted out to once per pass
(`:433`). So setup pays one global update per endpoint per pass; hold amortizes
one global update across all endpoints. **The restructuring this document
proposes for setup is not hypothetical — hold already does it.**

Meanwhile, on the OpenSTA side, three structural facts suggest the incremental
cone has little parallelism to offer in the first place:

1. `Levelize::level_space_` is 10 (`search/Levelize.hh:109`), so ~90% of level
   slots are permanently empty, yet the visit loop scans every index in the
   cone's span.
2. `visitParallel` falls back to a serial visit when a level holds fewer
   vertices than threads (`search/Bfs.cc:175`).
3. The dirty cone self-truncates wherever arrivals stop changing.

If dirty-cone levels typically hold a handful of vertices, then the per-level
`std::vector<Vertex*>` — the one index-computable structure in the whole
traversal — is only a few entries long, and **neither thread parallelism nor
memory-level parallelism has material to work with.** That would make the answer
not a wider machine but a restructured caller.

## The improvement idea: fix the shadow, not OpenSTA

Landing changes in OpenSTA is expensive in practice, so the remedy must not
require it. The alternative is to **extract into an algorithm-specific shadow —
flat, SoA where fields are read together, level-renumbered, index-computable —
run the algorithm on the shadow, and write back at the end.** That fixes the
access pattern and sidesteps the change-control problem at once, and it touches
only the caller.

**OpenROAD already does this twice: once well, once badly. That is the argument,
and it is sourced entirely in-tree.**

- `gpl` extracts the odb netlist into `gCellStor_` / `gNetStor_` / `gPinStor_`
  (`gpl/src/nesterovBase.h:1015-1017`), runs thousands of Nesterov iterations
  entirely on the shadow, and writes back at the end. **The architecture is
  therefore already accepted practice in this codebase.** But the shadow is AoS
  cross-linked by raw pointers — 104-byte `GCell`, 80-byte `GPin`, 112-byte
  `GNet` — which is why its hottest loops consume 8 useful bytes per line. It
  paid the extraction cost and then discarded most of the benefit.
- `drt` builds a per-worker `FlexGridGraph` shadow: flat 1-D, `Node` bit-packed
  to 16 bytes with `static_assert(sizeof(Node) == 16)`
  (`drt/src/dr/FlexGridGraph.h:1126`), fast axis transposed per layer, sized to
  stay in cache. That one works.

**The extraction boundary is already in the right place; the layout on the far
side of it is the defect.** External precedent agrees: the GPU STA work flattens
RC trees into 1-D BFS-order arrays, and IncreGPUSTA adopts dual-CSR adjacency —
the same conversion, done as a shadow and synced back.

Three preconditions, stated honestly, because they decide whether this works:

1. **Fidelity is the cliff, and scoping avoids it.** A vertex does not have *an*
   arrival; it has one per `Tag`, and the `Tag`/`TagGroup` machinery exists for
   exceptions, generated clocks, CPPR, multi-corner/multi-mode and latches. A
   one-float-per-vertex shadow is simply wrong on any design with exceptions.
   The version that survives contact is narrower: **the shadow is a fast
   approximate oracle for *screening* candidate moves, and OpenSTA remains the
   judge on the winner.** Approximation is then legal, because it only reorders
   candidates — and rsz already has the shape, since the MT policy generates and
   estimates a candidate set before committing.
2. **The topology snapshot is valid exactly between commits.** Fanin/fanout
   change only when a move lands, so a CSR built once per pass stays valid
   across that pass's queries. That is both the enabling property and the bound
   on how much can be batched.
3. **Build cost amortizes only in the regime the literature describes.**
   Building the shadow is itself one streaming pass of the pointer chase being
   eliminated. It pays only because optimization "can call a timer millions or
   even billions of times" — a precondition to check, not to assume.

A side effect worth naming: a level-renumbered CSR shadow is **smaller** than
what it shadows — tens of MB against OpenSTA's ~850 MB at 1 M vertices.
Shrinking the working set is the same lever as raising MLP, because an MSHR
covers a line either way.

## Proposed patches, minimum churn first

Carried here as patches and reported as upstreaming candidates; OpenROAD stays
read-only under this repo's moratorium.

1. **drt** — match the DRC cost-stamping loop nest to `getIdx`'s per-layer fast
   axis (`FlexDR_maze.cpp:365`, `:800`, `:921`). The stamps are independent
   increments on distinct cells, so this is **bit-exact**: 16/64 to 64/64 on
   horizontal layers, no QoR risk, no golden churn. The cheapest real
   measurement in the set.
2. **grt** — merge `parent_x1_/y1_/x3_/y3_` into one record. Over-split SoA is
   the defect here, the mirror image of gpl's.
3. **gpl** — split the hot fields out of the 80-byte `GPin` (`cx_`, `cy_` are
   read alone by HPWL and the density-center scatter). Changes no OpenSTA code.
4. **rsz** — hoist `findRequireds()`/`updateParasitics()` out of the per-endpoint
   pass loop, the way `RepairHold.cc:433,503` already does for hold.
5. **Only then** — an STA screening shadow, scoped to candidate ranking.

## The campaign

1. **Measure incremental level width first.** It is a property of the design and
   the algorithm, not of the machine, so it needs no special host — and it
   decides whether the rest of this is about microarchitecture at all.
   **Preregistered null: if dirty-cone levels hold O(1)-O(10) vertices, the
   answer is batching the caller, not widening the machine** — and that is a
   publishable result, not a failed experiment.
2. **Score loops on the Chou limiter list, not on stall fraction.** Ainsworth
   shows memory-bound vs compute-bound is not a meaningful dichotomy for these
   patterns on out-of-order cores. Measure: achieved and conditional MLP,
   fill-buffer-full cycles (to separate "code is not asking" from "machine is
   saturated"), instructions per LLC miss, demand vs prefetch occupancy, and —
   as a first-class term, not a footnote — branch mispredicts and window-resteer
   cycles.
3. **A/B the bit-exact drt loop-nest fix**, which isolates line occupancy from
   everything else.
4. **A/B a re-laid-out gpl shadow against the existing one.** This is the
   decisive cheap experiment: gpl's shadow already exists, its layout is the
   known-bad one, and changing it requires no OpenSTA work at all. If a
   level-renumbered, split-field gpl shadow does not move the needle, the STA
   shadow — far more expensive to build, and the one with the fidelity cliff —
   is not worth attempting.

### What the campaign host must provide

Requirements, in the order they will kill the campaign if unmet:

1. **Bare metal, with guest PMU access.** Cloud VMs generally do not expose
   performance counters to guests, so a rented host has to be a metal instance.
   Without this, every arm except experiment 1 is dead on arrival — check it
   before committing budget.
2. **A miss-occupancy counter, or a documented substitute.** The recipe is
   vendor-specific and Arm 2 is written twice depending on the answer: some PMUs
   expose outstanding-miss occupancy directly, so MLP is one division; others
   have no equivalent and the arm must be rebuilt around miss-allocation counts
   plus per-load latency sampling. Decide the vendor before writing the arm, not
   after.
3. **Enough counters to avoid multiplexing, or budget for repeat runs.** The
   metric set exceeds what most PMUs count simultaneously. Split into groups
   small enough to run unmultiplexed and re-run the stage per group — which is
   affordable only because stage replay is cheap; see below.
4. **RAM comfortably above the largest working set**, so nothing swaps: budget
   for ~850 MB of timing state at 1M vertices plus 300+ MB of global-route
   state, times the thread count where state is per-worker.
5. **Stable frequency.** Pin the governor and disable turbo, or report ratios
   (per-cycle, per-instruction) rather than wall-clock. Counter *ratios* survive
   frequency drift; elapsed time does not.
6. **Record the LLC size and thread count as study parameters.** Scope depends
   on working set versus LLC, so the same design can be a DRAM problem on one
   host and not on another. A result without these recorded is not portable.

Beyond correctness, the campaign wants the **widest instruction window and the
most outstanding-miss capacity available**, since that is the axis under test —
but note this buys headroom on the index-computable loops only. No host setting
raises a load-derived loop above MLP 1.

Stage replay makes the repeat runs affordable: each ORFS stage has a companion
`_deps` bundle that freezes its inputs, so a single stage can be re-run under
different counter groups without rebuilding the flow.

## KPI guidance

- **Calibrate to 1.2-1.35x, not to multiples,** for anything that is essentially
  a prefetch schedule on an index-computable loop. That is what Ainsworth
  measured on out-of-order cores, and saying so before the run stops a real
  result being read as a failure.
- **The shadow-layout arm is exempt from that calibration.** It changes the
  working-set size and the head class, not the prefetch schedule, so it is not
  the case Ainsworth measured.
- **A stage whose shadow fits in L3 is out of scope, and say so rather than
  reporting "no MLP problem".** drt is already known to be in this category.
- **Report useful bytes per line alongside every MLP number.** An MSHR covers a
  line; a loop that doubles its line utilization has done the same work as one
  that doubles its outstanding misses.

## Provenance

| claim | status |
| --- | --- |
| prefetch / SIMD / `omp simd` counts, `#pragma omp` per tool | verified at pinned OpenROAD `c7e5e751` |
| `-march`/`-mtune` absent; build is `opt` not `--config=opt` | verified |
| gpl / grt / drt / rsz / est loop shapes, sizes, line occupancy | verified at pinned OpenROAD `c7e5e751` |
| OpenSTA `Path` = 48 B, `Delay` = `std::array<float,4>`, virtual `DelayOps` | verified at pinned OpenSTA `65bd9df5` |
| OpenSTA linked-list edges, `VertexSet` = `std::set`, `ObjectTable` blocks of 128 | verified at pinned OpenSTA `65bd9df5` |
| `level_space_` = 10; serial fallback below `thread_count` | verified at pinned OpenSTA `65bd9df5` |
| **incremental dirty-cone level width** | **not measured — inference from queue structure and cone truncation. Experiment 1.** |
| achieved MLP, mispredict rates, line utilization in practice | **not measured — needs the campaign host.** |

Struct sizes are computed by hand from field lists at the pinned commits for
x86-64 with natural alignment; they have not been confirmed against a compiled
binary.
