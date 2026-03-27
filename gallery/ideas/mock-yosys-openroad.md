# Mock Yosys and OpenROAD for Seconds-Fast Configuration

## Problem

Setting up hierarchical synthesis for megaboom (93 modules, 35 memories)
took **2.5+ hours of developer time** across 8+ failed iterations, despite
the successful build itself taking only 7 minutes. Every single failure was
detectable statically from the SystemVerilog source and BUILD.bazel
configuration — no real synthesis or place-and-route was needed to find them.

The root cause is a feedback loop measured in minutes (37 minutes for a
single synthesis attempt), combined with cryptic error messages that don't
explain what went wrong or how to fix it. Claude can close this loop
autonomously — but only if it has a fast oracle that validates configuration
in seconds, not minutes.

### The pain: a narrative with numbers

Here is the actual timeline from the megaboom setup session:

**Attempt 1** (37 min): Synthesized BoomCore with `SYNTH_BLACKBOXES` for
35 memory modules. Synthesis completed, then `synth_odb` failed with
`[ERROR ORD-2013] LEF master regfile_20x12 not found`. Blackboxed modules
have no LEF — `synth_odb` can't load them into OpenROAD. A mock would
catch this in <1s: "35 blackboxed modules have no LEF. Use save_odb=False."

**Attempt 2** (5 sec): Tried `orfs_flow(..., save_odb=False)`. Instant
Bazel analysis error — `orfs_deps() got an unexpected keyword argument
'save_odb'`. The `orfs_flow` macro leaks `**kwargs` to sub-rules. A mock
would flag: "save_odb is not valid on orfs_flow. Use orfs_synth directly."

**Attempt 3** (5 sec): Tried `last_stage="synth"` to avoid downstream
rules. Same kwargs leak. Cost 5 seconds of build time but 10 minutes of
reading `flow.bzl` to understand why `last_stage` doesn't filter kwargs.

**Attempt 4** (37 min): Changed to memory-only blackboxes (not
KEPT_MODULES). Same ORD-2013 error — the root cause was always
`synth_odb`, not the blackbox list scope. Most painful iteration: 37
minutes to rediscover the same root cause.

**Attempt 5** (20 min reading + 10 sec build): Read three files in
bazel-orfs source (rules.bzl, flow.bzl, attrs.bzl). Discovered
`orfs_synth` exists as a separate rule that accepts `save_odb` directly.
Used `orfs_synth(save_odb=False)` — BoomCore synthesized in 10 seconds.

**Attempt 6** (15 min, 3 sub-iterations): SDC constraint failures.
`get_ports reset` on modules without reset. `get_ports -quiet clock clk`
fails (STA-0566: only one positional arg). `return` outside a proc in SDC.
Each fix required a 5-minute rebuild. A mock SDC validator would catch all
three in one pass.

**Attempt 7** (10 min): `output_group = "1_synth.v"` produced empty
filegroups — silent failure. Renamed to `1_2_yosys.v` after reading
SYNTH_OUTPUTS in rules.bzl. A mock would flag: "output_group '1_synth.v'
matches no outputs. Did you mean '1_2_yosys.v'?"

**Attempt 8** (5 min): Test regex `^\s+[A-Za-z].*_[0-9]+.*\(` didn't
match ASAP7 cell names (`DFFHQNx1_ASAP7_75t_R \REG_2$_DFF_P_`). All 93
modules reported FAIL. Quick fix to match `_ASAP7_` instead.

| Category | Time spent |
|----------|-----------|
| Failed build wall time | ~65 min |
| Reading bazel-orfs source | ~60 min |
| Debugging SDC issues | ~15 min |
| Debugging filegroup/test | ~20 min |
| **Total wasted time** | **~2.5 hours** |
| Successful final build | 7 min |
| Distinct configuration iterations | 8+ |

### Developer fatigue model

Working with Claude on EDA configuration creates a compounding fatigue
pattern. Each iteration requires:

1. **Approve** (~30s) — read Claude's proposal, evaluate if it makes sense
2. **Wait** (5s–37min) — decide whether to watch or context-switch
3. **Read** (~2min) — scan 200+ lines of output for the actual error
4. **Correct** (~3min) — translate domain knowledge into a fix Claude can act on

By iteration 4, the developer is skimming approvals, switching to other
work during waits, reading error output less carefully, and providing less
precise corrections. This is the **fatigue spiral**: less attention → worse
corrections → longer wait for worse results → more fatigue.

| Iter | Action | Wall time | Running total |
|------|--------|-----------|---------------|
| 1 | Approve synth, wait 37 min, explain LEF issue | 42 min | 42 min |
| 2 | Approve save_odb fix, instant fail, explain kwargs | 3 min | 45 min |
| 3 | Approve last_stage fix, same leak | 3 min | 48 min |
| 4 | Approve memory-only blackboxes, wait 37 min, same error | 42 min | 90 min |
| 5 | Direct Claude to read source, eureka: orfs_synth | 25 min | 115 min |
| 6a-c | Three SDC iterations | 24 min | 139 min |
| 7 | Debug empty filegroup | 15 min | 154 min |
| 8 | Fix test regex | 5 min | 159 min |
| **Final** | **Approve real build, wait 7 min, success** | 7 min | **166 min** |

## Idea

Two Python scripts — `mock_yosys.py` and `mock_openroad.py` — plus an
orchestrator `mock_flow.py`. They parse SystemVerilog source and BUILD.bazel
configuration, then produce mock output files with heuristic estimates.
The entire megaboom flow (93 modules × synth + floorplan + placement) in
2–3 seconds. All configuration errors caught in one pass.

### Architecture: standalone Python, no Bazel

The scripts run **outside Bazel**, directly on the filesystem:

- Bazel analysis takes 5–10s per target even with warm cache
- 93 targets × 5s = 7+ minutes just for Bazel overhead
- Standalone Python: parse all 93 modules in <1 second
- No need to modify bazel-orfs rules or create custom toolchains
- Can run in CI without Docker/ORFS installed

```
mock_flow.py --build megaboom/BUILD.bazel --sv bazel-bin/megaboom/BoomTile.sv
```

### What mock_yosys.py does

**Input**: SystemVerilog source, module name, SYNTH_BLACKBOXES, SDC file,
ORFS arguments.

**Output** (matching real ORFS names/formats):

- `1_2_yosys.v` — Mock netlist with synthetic cell instantiations
  proportional to estimated gate count, using ASAP7 naming conventions.
- `synth_stat.txt` — Per-module cell count and area estimates in Yosys
  report format (parseable by `scripts/module_sizes.py`).
- `mem.json` — Inferred memories from `reg [W-1:0] name [0:D-1]` patterns.

**Cell count heuristics** (order of magnitude, not accuracy):

| Source construct | Estimated cells |
|-----------------|----------------|
| `reg [N-1:0] x` | N flip-flops |
| `assign y = a + b` (N-bit) | ~N cells |
| `assign y = a * b` (N-bit) | ~N^1.5 cells |
| `always_comb` block (M lines) | ~2M cells |
| `case` (K cases, N-bit) | ~K×N cells |
| Module instantiation (not blackboxed) | Recursive sum |

### What mock_openroad.py does

**Input**: Mock netlist, module name, ORFS arguments (CORE_UTILIZATION,
PLACE_DENSITY, DIE_AREA, PDN_TCL, MACRO_PLACE_HALO), macro LEF/LIB.

**Output** (per stage):

- `<module>.lef` — Mock LEF with realistic SIZE from area/utilization.
  This is the **critical output** — parent modules consume it for macro
  placement.
- `<module>_typ.lib` — Mock Liberty with pin list from module ports.

### What errors mock_flow.py detects

| # | Error class | Megaboom time saved |
|---|------------|-------------------|
| 1 | `save_odb` on `orfs_flow` | 75 min (attempts 2–4) |
| 2 | LEF master not found | 37 min (attempt 1) |
| 3 | SDC missing ports | 15 min (attempt 6) |
| 4 | SYNTH_BLACKBOXES typo | Silent failure |
| 5 | Wrong output_group | 10 min (attempt 7) |
| 6 | BLOCK vs BLOCKS PDN | Hours (if hit) |
| 7 | Hierarchy-only modules | Hidden complexity |
| 8 | IO regex mismatch | Routing congestion |
| 9 | Parallelism bottleneck | Planning info |
| 10 | Circular blackbox dependency | Hard to debug |

**Output format** — designed for Claude consumption:

```
mock_flow: megaboom/BUILD.bazel + BoomTile.sv
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✗ ERROR: constraints-module.sdc references port "reset" but 12 modules
         lack this port: ALUExeUnit, BranchKillableQueue_10, ...

⚠ WARNING: SYNTH_BLACKBOXES contains "ram_2x46" but no module named
           "ram_2x46" exists in BoomTile.sv (closest: "ram_2x460")

ℹ INFO: Estimated synthesis critical path: BoomCore (est. 72K cells, ~25 min)

0 errors → ready for real build
```

### How Claude uses this

**Before** (current state):
```
Human: "Set up megaboom hierarchical synthesis"
Claude: [generates BUILD.bazel] "Let me build..." [needs approval]
Human: Y → [waits 37 min] → error → correction → repeat 8+ times
```

**After** (with mock flow):
```
Human: "Set up megaboom hierarchical synthesis"
Claude: [generates BUILD.bazel, constraints, kept.bzl]
Claude: [runs mock_flow.py — 2 sec, no approval needed]
Claude: [reads errors, fixes, runs again — 2 sec]
Claude: "Configuration is ready. Mock validates 93 modules, 0 errors.
         Estimated synthesis: 25 min critical path. Ready to build?"
Human: Y → [one wait, one result, done]
```

| Metric | Without mock | With mock |
|--------|-------------|-----------|
| Developer approvals | 11+ | 1–2 |
| Total developer wall time | 166 min | ~15 min |
| Context switches | 8+ | 1 |
| Lines of error output to read | ~1,000 | 0 |

### Unit tests encode every gotcha

The test suite IS the specification — it captures every gotcha from the
megaboom experience as a reproducible assertion:

- `test_blackbox_nonexistent_module` — flags SYNTH_BLACKBOXES typos
- `test_sdc_missing_reset_port` — validates port references
- `test_sdc_multi_arg_get_ports` — catches STA-0566 pattern
- `test_orfs_flow_with_save_odb` — flags kwargs leak
- `test_filegroup_output_group` — flags outdated output_group names
- `test_pdn_block_vs_blocks` — validates PDN strategy for macro designs
- `test_mock_lef_grid_snap` — LEF SIZE snapped to ASAP7 grid
- `test_megaboom_full_flow` — integration test, <5 seconds, 0 errors on
  known-good config

### Ad-hoc procedures that should be scripts

During megaboom setup, Claude performed manual procedures that should be
reusable tools. Each was a manual sequence of shell commands and heuristic
reasoning, lost when the conversation ended:

1. **Verilog module discovery** — `grep "^module "` + manual cross-reference
2. **Memory module identification** — name pattern scanning (`ram_`, `regfile_`, etc.)
3. **KEPT_MODULES list generation** — copy upstream list, verify against generated Verilog
4. **Blackbox list construction** — per-module exclusion (`[b for b in ALL if b != name]`)
5. **SDC port validation** — manual `grep` of module ports vs SDC references
6. **IO constraint port matching** — regex validation against SRAM port names
7. **Synthesis profile analysis** — identify the tallest pole from `--profile`
8. **synth_stat.txt analysis** — cross-reference 0-cell modules against hierarchy
9. **Test result interpretation** — debug regex mismatches against actual netlist format

**`mock_flow.py` subsumes most of these.** Individual scripts can be
extracted later, but the orchestrator runs all validations in one pass.

### Connection to bazel-orfs GUI (PR #581)

The [bazel-orfs GUI](https://github.com/The-OpenROAD-Project/bazel-orfs/pull/581)
is a browser-based interface for monitoring ORFS builds. The mock flow is
the missing **intelligence layer** for its "intelligent assistance":

| GUI stage | What it does today | What mock flow adds |
|-----------|-------------------|-------------------|
| DAG view | Shows target graph | Annotates with estimated cell counts, flags errors |
| Config editor | Edits parameters | Validates changes instantly before building |
| Build launcher | Launches builds | Pre-validates → build succeeds on first attempt |
| Issue generator | Creates reproducers | Identifies which stage will fail, pre-packages context |

The vision: give every GUI user the same experience that Claude provides —
context-aware assistance that catches errors before they happen. The cycle:

1. Claude learns a gotcha (e.g., "save_odb doesn't work with orfs_flow")
2. Claude writes a test (e.g., `test_orfs_flow_with_save_odb`)
3. The test drives the mock (mock_flow checks for this pattern)
4. The GUI calls mock_flow (pre-validates before building)
5. **Every user benefits** — not just the one who hit the bug

### The LLM's remaining job: getting to Verilog

Everything above assumes you already have Verilog. For megaboom, **getting
to Verilog was the hardest part** (~9 hours): compiling Chisel through
5 libraries (cde → diplomacy → hardfloat → rocket-chip → boom), each
requiring Chisel 7 patches. The rocket-chip patch alone was 7,305 lines
across 300+ files.

This is quintessentially an LLM task: cross-language pattern recognition,
cross-project dependency tracing, Scala error interpretation, configuration
space exploration. No specialized tools exist (`chisel-migrate`, etc.).

The division of labor:

```
LLM DOMAIN (creative)     → .sv + BUILD.bazel + .sdc
MOCK FLOW (deterministic) → validation report + estimates
GUI (interactive)         → visual interface
REAL TOOLS (ground truth) → the actual chip design
```

The LLM gets to Verilog. The mock validates configuration instantly. The
GUI wraps both in an accessible interface. Real tools run once, correctly.

### Upstream improvements that would also help

In **bazel-orfs**: `orfs_flow` should accept `save_odb` (fix kwargs leak),
validate SYNTH_BLACKBOXES against Verilog source, validate output_group
names, and provide `orfs_per_module_synth` as a first-class macro.

In **ORFS**: `synth_odb` should handle missing LEF gracefully, provide a
`constraints-submodule.sdc` template, validate SYNTH_BLACKBOXES in the
Makefile.

In **OpenROAD**: better ORD-2013 error messages (suggest save_odb=False),
`link_design -check_only` dry-run mode, hierarchical `read_verilog` with
blackbox awareness.

### Files to create

| File | Purpose | Est. lines |
|------|---------|-----------|
| `scripts/mock_yosys.py` | Mock synthesis | ~300 |
| `scripts/mock_openroad.py` | Mock stages | ~300 |
| `scripts/mock_flow.py` | Orchestrator | ~200 |
| `scripts/mock_orfs_parser.py` | BUILD.bazel parser | ~200 |
| `scripts/tests/test_mock_flow.py` | Unit tests | ~400 |
| `scripts/tests/fixtures/` | Test .sv and BUILD snippets | ~200 |

Reuses: `scripts/analyze_hierarchy.py` (Verilog parser, ~250 lines),
`scripts/module_sizes.py` (synth_stat parser, ~115 lines).

## Impact

- **Configuration iteration**: hours → seconds (100–1000x speedup)
- **Developer fatigue**: 11+ approve/wait/read/correct cycles → 1–2
- **Context switches**: 8+ → 1 (the final real build)
- **Cognitive load**: scanning 1,000 error lines → reviewing a clean summary
- **Who benefits**: anyone setting up hierarchical ORFS designs, especially
  with Claude assistance
- **Side benefit**: mock heuristics document implicit contracts between
  BUILD.bazel configuration and tool behavior — currently learned only
  through painful experience
- **Side benefit**: test suite is a regression suite for configuration
  patterns — catches bazel-orfs API changes before humans rediscover them

## Effort

Medium (~1,600 lines Python, 2–3 days):
- `analyze_hierarchy.py` parser already exists (~250 lines, reusable)
- `module_sizes.py` synth_stat parser exists (~115 lines, reusable)
- BUILD.bazel parsing is string matching on a small set of rule types
- Mock output generation is templated text
- Error detection is cross-referencing parsed data
- Unit tests capture every gotcha as an assertion
