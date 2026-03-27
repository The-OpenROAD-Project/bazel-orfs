> **Repo**: Run from the openroad-demo root. `bazel build` targets are openroad-demo targets.

Analyze and fix errors from a bazel build.

The user may provide a failing build target or paste error output. Follow these steps:

## 1. Get the Error

If no error output is provided, run the build and capture the error:

```bash
bazel build <target> 2>&1 | tail -100
```

## 2. Diagnose the Error Type

### Synthesis errors (during _synth target)

**slang/Yosys parse errors:**
- Missing module: Check if all required Verilog files are included in `verilog_files`
- Unsupported SystemVerilog construct: Try switching `SYNTH_HDL_FRONTEND` from `slang` to `yosys` or vice versa
- Include file not found: Add the include directory to the external.BUILD.bazel or use `-I` flags
- Macro/define not set: Add defines to `SYNTH_SLANG_ARGS` or `ADDITIONAL_LEFS`

**Memory inference issues:**
- If large memories cause synthesis to hang: Ensure `SYNTH_MOCK_LARGE_MEMORIES=1` is set
- If memories are not being mocked: Check `SYNTH_MEMORY_MAX_BITS` setting

### Floorplan/placement errors

**Die area too small:**
- Increase `DIE_AREA` or switch to `CORE_UTILIZATION` mode
- Reduce `CORE_UTILIZATION` (try 30 or even 20)

**Macro placement failures:**
- Increase die area to give macros room
- Adjust `MACRO_PLACE_HALO`
- Check `MACRO_PLACE_CHANNEL` settings

### Routing errors

**GRT congestion:**
- Reduce `PLACE_DENSITY`
- Enable `GPL_ROUTABILITY_DRIVEN=1` (slower but helps)
- Increase die area

**DRC violations:**
- Check `MIN_ROUTING_LAYER` and `MAX_ROUTING_LAYER`
- May need to adjust `TAPCELL_TCL`

### Bazel/build system errors

**Missing dependency:**
- Check MODULE.bazel for missing `use_repo` calls
- Verify http_archive sha256 matches

**Python/genrule errors:**
- Check that requirements_lock.txt has all needed Python packages
- Verify the generator script works standalone first

## 3. Apply the Fix

- For Verilog issues: create a patch file in `<project>/patches/` and add to http_archive
- For build config issues: update the arguments dict in BUILD.bazel
- For constraint issues: update constraints.sdc
- For Bazel issues: update MODULE.bazel or external.BUILD.bazel

## 4. Verify

Re-run the failing target:

```bash
bazel build <target>
```

If it passes, run the next stage to check for cascading issues.

## 5. Update /demo-add

If this error revealed a new lesson, update `.claude/commands/demo-add.md`
with the fix so future projects avoid the same problem.
