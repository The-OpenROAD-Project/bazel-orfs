# Synthesis: yosys, slang, ABC and ORFS's synth scripts

ORFS's `flow/scripts/synth*.tcl`. yosys bans LLM-written pull requests
and comments: problems go there as issues with a minimal failing case,
fixes are carried here (`patches/yosys-*`).

## Where the time goes

- **The yosys Verilog frontend**: XSCore canonicalisation 400-457 s
  single-threaded at a few MB/s; slang ~1 min. `prefer-slang` skill.
  Exceptions where slang loses on period and runtime exist
  (VirtualStoreQueue, bazel-orfs #1456).
- **Re-canonicalisation per kept module**: one whole-design read per
  kept module, ~2.5 CPU-hours per XiangShan synthesis
  (`ideas/canonicalize-slicer.md`, not built).
- **`memory_dff`** built a walker for every module with or without
  memories: XSCore 721 -> 64 s with the memory passes run only where
  memories are (ORFS #4622, yosys #6282).
- **`extract_fa`**: 51-83 % of synthesis on vector/FMA modules.
  `SKIP_EXTRACT_FA` (carried 0074) for turnaround.
- A `-c fastbuild` yosys is ~15x slower: time with `-c opt`.

## Silent wrong answers

- **`abc -dff` is nondeterministic with more than one thread** (yosys
  #6170): `YOSYS_MAX_THREADS=1`, `SYNTH_REPEATABLE_BUILD=1`.
- **`abc_new` ignores `-script`** when "-script" appears anywhere in its
  arguments, e.g. a path under OpenROAD-flow-scripts (yosys #6320, carried
  yosys-0002).
- **`write_xaiger2` holes in hash order**: with two or more white boxes
  ABC `&verify` asserts, so every `SWAP_ARITH_OPERATORS` run skipped its
  post-map check (carried yosys-0001).
- **The SDC period never reaches ABC** when a script file is used:
  synthesis is clock-independent. A vendored speed script with `-D`
  made Frontend slower (bazel-orfs #1142). **Dead end.**
- `ABC_AREA=1` left on from a turnaround setting: speed script took
  6,186 -> 4,991 ps (bazel-orfs #1111).
- **Synthesis slack is meaningless** until `repair_design`: ABC leaves
  1,000+ fanout nets bare. Balancing them before floorplan barely helps
  once timing-driven placement is on (bazel-orfs #1125).
- `REMOVE_ABC_BUFFERS` (deprecated) left 96 % of slew violations;
  dropping it 5,681 -> 5,118 ps (bazel-orfs #1122).
- **`SYNTH_MINIMUM_KEEP_SIZE` counts macro area**, so it keeps memory
  wrappers by accident; on riscv32i the kept boundary sat on the worst
  path, flat is 5.2 % faster (ORFS #4714 open).
- A vendored clock gate synthesised as latch + AND: carried 0068
  techmap hook. abc hangs with TERM unset and TMPDIR >= 36 characters
  (yosys #6448).
- A 206 KB `SYNTH_BLACKBOXES` environment string exceeded the 128 KiB
  argument limit (fixed, ORFS #4798).
