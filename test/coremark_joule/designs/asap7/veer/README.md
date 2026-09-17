# VeeR EH1 in the CoreMark/Joule study: how it is wired

Design notes moved out of the study's paper (`test/coremark_joule/README.md`,
§7) so that the paper carries results and this file carries mechanics.
The results stay there: 4.798 CoreMark/MHz against Western Digital's
published 4.94, and zero external transfers per hot CoreMark iteration.

**What is worth taking from ORFS's design, and what is not.** The
useful half is everything that is not RTL. ORFS's
`ADDITIONAL_LEFS`/`ADDITIONAL_LIBS` harden the ICCM/DCCM and
instruction-cache arrays as macros — `fakeram7_2048x39`,
`fakeram7_256x34`, `fakeram7_64x21` — with LEF and Liberty views
checked in; the design is therefore an existence proof that this core
can be hardened at the boundary §3.1 asks for, and the views, the SDC,
`io.tcl` and the utilisation are a working starting point. Its
`SYNTH_KEEP_MODULES` is also, already, the enumeration §3.7 asks for:
`ifu_ifc_ctl`, `ifu_aln_ctl`, `ifu_bp_ctl`, `ifu_mem_ctl` (fetch),
`dec_decode_ctl`, `dec_ib_ctl`, `dec_tlu_ctl` (decode and control),
`dec_gpr_ctl_*` (register file), `exu`, `exu_alu_ctl`, `exu_div_ctl`
(execute), `lsu_dccm_ctl`, `lsu_dccm_mem`, `lsu_bus_buffer`,
`lsu_stbuf`, `lsu_lsc_ctl` (load/store), `pic_ctrl`, and the two
instruction-cache tag and data modules. A `units.json` for it is a
mapping exercise rather than a research one.

**The RTL is not usable for this study, and the reason is specific.**
ORFS vendors the core as a single 6.3 MB file,
`flow/designs/src/swerv/swerv_wrapper.sv2v.v`. Its own README records
what it is: SweRV EH1 1.1, cloned from
`westerndigitalcorporation/swerv_eh1` at commit `3ef7e65f`, with "the
default configuration from Repository" applied. Three consequences
follow, and they compound:

- It is a **mechanical sv2v translation** of SystemVerilog into
  Verilog-2005, flattened into one file. Whether it still simulates,
  and whether it simulates as the original does, is not established by
  anything in the repository. Nothing in this study's chain would
  notice a translation artefact that changes behaviour without
  breaking synthesis — except the CRC gate, which is exactly why that
  gate exists, but a core that fails it tells us nothing about VeeR.
- **The configuration is baked in and unrecorded.** VeeR's ICCM, DCCM,
  instruction-cache and branch-predictor sizes come from a generator
  (`configs/swerv.config`) whose output is a defines header. That step
  happened once, before the sv2v pass, and the chosen settings are not
  in the repository. "The default configuration" is not a statement
  anyone can check, and the L1 sizes are precisely what §3.1 makes
  load-bearing.
- It is the **pre-CHIPS-Alliance snapshot**. Upstream is now
  `chipsalliance/Cores-VeeR-EH1`, five minor releases further on.

So EH1 is wired the way every other core in this study is wired: from
its own upstream repository, at a pinned commit, through the module
graph — not from a vendored, pre-converted copy. The configuration is
generated once from upstream's own generator and **committed** as a
defines header with its provenance, for the same reason `rtl/cmj_*.v`
exists: the core that is simulated and the core that is hardened must
not be able to differ, and a reader must be able to see which
configuration was measured. (Upstream's generator is Perl, which is why
its output is committed rather than run in the build.)

**Its CoreMark/MHz is 4.94, and upstream says on what.** The figure
comes from Western Digital's own `seh1_SweRV_CoreMark_Benchmarking.pdf`
[11], and the configuration it was measured on is not one of the
generator's target presets:

    swerv -set reset_vec=0xf0090000 -set=iccm_enable=1
          -unset=icache_enable
          -iccm_region=0xf -iccm_offset=0x90000 -iccm_size=64
          -dccm_region=0xf -dccm_offset=0x80000 -dccm_size=64
          -btb_size=512 -bht_size=2048

64 kB ICCM holding the code, 64 kB DCCM holding the data, the
instruction cache **off**, and a 512-entry BTB with a 2048-entry BHT.
A default-target build has a 32-entry BTB and a 128-entry BHT — a
sixteenth of each — so a number taken on the default branch predictor
would not be comparable with the published one at all.

**This study keeps their branch predictor and swaps their ICCM for the
instruction cache**, and the reason is the gate-level run rather than a
preference:

    swerv -set=icache_enable=1 -icache_size=16 -unset=iccm_enable
          -dccm_region=0xf -dccm_offset=0x80000 -dccm_size=64
          -btb_size=512 -bht_size=2048
          -ahb_lite -set=fpga_optimize=0

- **The ICCM cannot be filled by the core.** `lsu_addrcheck.sv` uses the
  ICCM region only to suppress side-effects; there is no store path from
  the LSU into it. Upstream's testbench fills it by forcing values
  straight into `ram_core` down a hierarchical path, and their FPGA flow
  does it over JTAG with extended OpenOCD abstract commands. Neither
  survives to a gate-level netlist, where the ICCM is a hardened macro
  with no `ram_core` to force — and the gate-level run is the one that
  produces the SAIF. Filling it properly would mean a DMA master pushing
  the image in over the AHB slave port before the benchmark starts: real
  machinery, outside the boundary, existing only to work around the load
  path.
- **The icache needs no loader.** The program sits in external memory
  and is fetched through the cache, so the same image boots in RTL and
  at gate level with nothing forced.
- **It is the cache this study says it measures.** §3.1's boundary is
  the core and its L1; with the cache on, the L1 is exercised rather
  than configured away, and the hot loop runs entirely inside the
  hardened block — instructions from the icache, data and stack from the
  DCCM.

What that leaves outside the boundary is the residual miss traffic, and
it is measured rather than assumed: the SoC wrapper counts IFU bus
transactions, so "CoreMark fits in the instruction cache" is a number in
the results rather than a claim in a comment.

The memory shapes that fall out — `ram_256x34` (icache data),
`ram_64x21` (icache tag) and `ram_2048x39` (DCCM) — are exactly the
three fakeram7 views ASAP7 already carries. A 32 kB icache would need
`ram_512x34` and `ram_128x21`, which it does not.

Two further departures from Western Digital's setup, both deliberate.
`-ahb_lite`, because the external bus here serves only the boot image
and the two-word sim-control device of §3.2, and AHB-Lite is a far
smaller adapter than AXI4 for that. And `fpga_optimize=0`: their number
was taken on a Nexys-4 FPGA prototype at 40 MHz, where the generator's
FPGA setting minimises clock gating — a first-order term in exactly the
energy this study reports.

**Two slang flags it does not compile without**, both found by running
the frontend on it directly rather than guessed, and both properties of
the RTL rather than of this study:

- `--single-unit`. SystemVerilog makes each file its own compilation
  unit, so a macro defined in one is invisible in the next. VeeR's
  entire configuration is macros — every `RV_*` in
  `common_defines.vh` — and its own `flist.questa` assumes a
  single-unit flow by listing that file first. Without the flag every
  reference to a configuration macro is an "unknown macro or compiler
  directive", and no amount of file ordering helps. **Verilator hides
  this difference by making macros global**, which is exactly why the
  simulator built long before the flow did — a reminder that
  "it simulates" and "it synthesises" are separate claims.
- `--allow-use-before-declare`. VeeR declares signals after the always
  blocks that use them, in `dec.sv` among others. The LRM requires
  declaration first for variables and slang enforces it; yosys's own
  reader and Verilator do not.

Both live in `SYNTH_SLANG_ARGS` in the design's `config.mk`, with the
reason next to them.

Getting to them took the `_deps` reproducer rather than the build log,
and that is worth recording too: ORFS's `synth.sh` routes the frontend's
output through `run_command.py`, and slang's diagnostics — which go to
stderr — do not reach the stage log. The log ends at
`Executing SLANG frontend.` / `ERROR: Compilation failed`, which names
neither the file nor the reason. Running the frontend by hand is what
turned that into twenty lines of exact errors.
