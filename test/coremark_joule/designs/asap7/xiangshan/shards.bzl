"""XiangShan's power shards: XSTile and every unit hardened inside it."""

# The parent's scope in every simulation's SAIF: XSTile's instance, cm_soc
# -> outer (CoreMarkJouleSoC) -> soc (XSTop) -> core_with_l2, read off the
# SoC's split Verilog; the first capture traced nothing at "inner".
XS_SAIF_SCOPE = "TOP/cm_soc/outer/soc/core_with_l2"

# Instance path in XSTile -> the unit's flow (a block, or a register file
# made by _regfile_macro). The paths are the kit snapshot's
# (kit/snapshot/floorplan), from the tile synthesised whole; a unit's
# parent shard checks each against its own ODB, and the sum fails on a
# wrong path or scope.
XS_SHARDS = {
    "core/backend/inner_ctrlBlock/rob/rab/renameBuffer": "RenameBufferFile",
    "core/backend/inner_ctrlBlock/rob/robEntryFile": "RobEntryFile",
    "core/backend/inner_fpRegion": "FltRegionModule",
    "core/backend/inner_fpRegion/fpRegFile": "FpRegFile",
    "core/backend/inner_intRegion/intDataPath/intRegFile": "IntRegFile",
    "core/backend/inner_vecRegion": "VecRegionModule",
    "core/backend/inner_vecRegion/vfRegFile": "VfRegFile",
    "core/frontend": "Frontend",
    "core/frontend/inner_ftq/entryQueue": "FtqEntryQueue",
    "core/frontend/inner_ftq/metaQueueCommit": "FtqMetaQueueCommit",
    "core/frontend/inner_ftq/metaQueueRedirect": "FtqMetaQueueRedirect",
    "core/frontend/inner_ftq/metaQueueResolve": "FtqMetaQueueResolve",
    "core/memBlock": "MemBlock",
    "l2top/inner_l2cache": "CoupledL2",
}

# The hardened blocks among them (the rest are register files).
XS_BLOCK_UNITS = ["CoupledL2", "FltRegionModule", "Frontend", "MemBlock", "VecRegionModule"]

# Every unit whose netlist the replays need, XSTile first.
XS_SHARD_SIMS = ["XSTile"] + sorted(XS_SHARDS.values())

# XSTile's instance in the simulation, dotted below Verilator's root: the
# capture's trace configuration and the replays' capture scopes.
XS_TRACE_ROOT = XS_SAIF_SCOPE.removeprefix("TOP/").replace("/", ".")

# Simulation shards cut out of a unit (shard_replays' cuts): instance
# paths of kept modules below it, from each unit's global-route census
# (`<unit>_grt_census`), so that every piece, the remainder included, is
# under ~0.5M instances (Verilator at 20-40 KB an instance, 24 GB);
# XSTile's own remainder is replayed in a bigger scope.
XS_SHARD_CUTS = {
    # XSTile without its hardened units: 2,088,633 instances at synthesis
    # (cmj_xiangshan_census; no global route of the parent yet). Out: the
    # CtrlBlock's decode, dispatch, memCtrl and rename, the integer
    # region's ExuBlock and its thirteen issue queues (1,428,000 between
    # them); the Rob stays, it holds two register files. ~0.66M left,
    # replayed after the blocks, in a bigger scope.
    "": ["core/backend/inner_ctrlBlock/" + m for m in ["decode", "dispatch", "memCtrl", "rename"]] +
        ["core/backend/inner_intRegion/intExuBlock"] +
        ["core/backend/inner_intRegion/issueQueue" + q for q in [
            "ALU0BJU0_AluCsrFenceLinkBrhNjmp",
            "ALU1BJU1_AluDivBrhNjmp",
            "ALU2BJU2_AluI2fBrhNjmp",
            "ALU3_AluBkuVset",
            "ALU4_AluMul",
            "ALU5_AluMul",
            "LDU0_Ldu",
            "LDU1_Ldu",
            "LDU2_Ldu",
            "STA0_StaMou",
            "STA1_StaMou",
            "STD0_StdMoud",
            "STD1_StdMoud",
        ]],
    # 1,195,686 at global route: the two big issue pipes (401,979 and
    # 421,353) out, 372,354 left
    "core/backend/inner_vecRegion": ["issuePipes", "issuePipes_1"],
    # 1,582,077: the BPU's predictors (not the BPU whole, 804,981, which
    # at a flop-heavy 40 KB an instance would not fit 24 GB), the IFU,
    # the ICache, the Ftq's resolve queue, the IBuffer and the ITLB out
    # (1,082,894), ~499,000 left
    "core/frontend": [
        "inner_ifu",
        "inner_bpu/tage",
        "inner_bpu/sc",
        "inner_bpu/phr",
        "inner_bpu/abtb",
        "inner_bpu/ittage",
        "inner_bpu/utage",
        "inner_icache",
        "inner_ftq/resolveQueue",
        "inner_ibuffer",
        "inner_itlb",
    ],
    # 2,752,934: the fourteen largest kept modules out (2,277,909), ~475,000
    # left
    "core/memBlock": [
        "inner_dcache",
        "inner_lsq.loadQueue.loadQueueReplay",
        "inner_lsq.storeQueue.physicalQueue",
        "inner_ptw",
        "inner_sbuffer",
        "inner_dtlb_ld_tlb_ld",
        "inner_lsq.storeQueue.virtualStoreQueue",
        "inner_prefetcher",
        "inner_lsq.loadQueue.uncacheBuffer",
        "inner_dtlb_st_tlb_st",
        "inner_lsq.loadQueue.loadQueueRAR",
        "inner_dtlb_prefetch_tlb_prefetch",
        "inner_uncache",
        "inner_lsq.loadQueue.loadQueueRAW",
    ],
}

# The cuts the replays take, two-level (shard_replays' two_level): a kept
# module's global-route netlist carries input ports its RTL module lacks
# (hierarchical repair buffers a module's net outside it and feeds it back
# through a new port), so a cut is replayed from its unit's replay, which
# records the stub's every port, not from the RTL capture. MemBlock and
# XSTile, whole, are over what a replay can take (55-110 GB inferred);
# every other unit is replayed whole.
XS_REPLAY_CUTS = {u: [
    c
    for c in XS_SHARD_CUTS[u]
    # its netlist has punched outputs (r_0, r_1, ...): the logic outside
    # reads nets only it computes, so it stays in MemBlock's own replay
    if c not in ["inner_lsq.storeQueue.physicalQueue"]
] for u in ["", "core/memBlock"]}

# The cuts whose level-2 replay compares its outputs only from the cycle
# after the captured reset first falls (shard_replays'
# compare_from_reset): values before it are the simulators' initial
# ones, not the design's. intExuBlock's io_in_0_0_ready reads 1 in the
# capture and 0 in the netlist at time 0, before reset ever rose (it
# rises at 236 ps and falls at 8,968 ps, the clock at 473 ps). None in the
# first pass, which counts what differs instead (XS_COUNT_OUTPUTS); for
# the second.
XS_FROM_RESET = []

# The cuts whose level-2 replay counts the outputs that differ from the
# RTL instead of stopping at the first (shard_replays' count_outputs),
# their SAIF taken as produced. The first pass takes dcache's so: its
# outputs differ from the RTL at cycle 10223, io_sms_agt_evict_req_bits_
# vaddr bit 33, while valid; `<replay>_outputs.json` says how much.
XS_COUNT_OUTPUTS = [
    # second pass: every two-level piece counted, not stopped; the pin says
    # how many outputs differ from the RTL, from when (the run's ruling:
    # differences counted and reported, not investigated)
    (u + "/" if u else "") + c
    for u, cs in XS_REPLAY_CUTS.items()
    for c in cs
]

# The kept modules each not-yet-built unit could be cut along
# (plan/plan.bzl's SYNTH_KEEP_MODULES), largest expected first. Once the
# unit's grt ODB exists, its census (`<unit>_grt_census`) gives each
# module's instance paths and cells; the cuts are the fewest of these
# that bring every piece, remainder included, under ~0.8M cells (24 GB of
# Verilator at ~23 KB a cell), entered in XS_SHARD_CUTS by instance path.
# A candidate whose module the census does not list is dropped, never
# guessed.
XS_CUT_CANDIDATES = {
    "Frontend": ["ICache", "Bpu", "Ifu", "Ftq", "IBuffer", "Ittage", "Tage", "Sc", "MicroTage", "AheadBtb"],
    "MemBlock": [
        "DCacheWrapper",
        "L2TLBWrapper",
        "Sbuffer",
        "LoadQueueReplay",
        "VirtualStoreQueue",
        "LoadQueueRAR",
        "LoadQueueRAW",
        "PrefetcherWrapper",
        "TLBNonBlock",
        "TLBNonBlock_1",
        "TLBNonBlock_2",
    ],
    "XSTile": ["L2Top", "CtrlBlock", "DataPath", "ExuBlock", "NewCSR", "Rob", "Rename", "Dispatch"],
}

# The replays' Verilator options: sim/BUILD.bazel's gate options.
XS_REPLAY_VOPTS = [
    "--trace-underscore",
    "--output-split",
    "20000",
    "--output-split-ctrace",
    "3000",
    "-Wno-IMPLICIT",
    "-Wno-MODDUP",
    "-Wno-PINMISSING",
    "-Wno-STMTDLY",
    "-Wno-SPECIFYIGN",
    "-Wno-WIDTH",
    "-Wno-UNOPTFLAT",
    "-Wno-CASEINCOMPLETE",
    "-Wno-TIMESCALEMOD",
    "-Wno-UNUSEDSIGNAL",
    "-Wno-DECLFILENAME",
    "-Wno-VARHIDDEN",
]

def xs_replay(path):
    """The replay target of a unit or cut below XSTile (shard_replays' naming)."""
    return "cmj_xiangshan_replayed_" + ("parent" if path == "" else "".join([c if c.isalnum() or c == "_" else "_" for c in path.elems()]))
