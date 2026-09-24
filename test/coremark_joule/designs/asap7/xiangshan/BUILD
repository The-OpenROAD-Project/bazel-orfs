load("@bazel-orfs//:openroad.bzl", "odb_debug", "orfs_flow")
load("//test/coremark_joule/flow:power.bzl", "census_probe", "grt_netlist", "hier_probe", "physical_probe", "stage_power", "stage_power_units")
load(":plan/plan.bzl", "PLAN")
load(":xiangshan.bzl", "xiangshan_flow")

exports_files(["constraints.sdc"])

# The parent's three placed netlists, at real size in a parent of flops:
# the battery's rung for what the resizer, CTS and the router do to an
# array of this size (test/structured_netlist, scaffold.bzl).
exports_files(
    [
        "IntRegFile.regfile",
        "RenameBufferFile.regfile",
        "RobEntryFile.regfile",
    ],
    visibility = ["//test/structured_netlist:__pkg__"],
)

# Every candidate module of the macro selection hardened as a block behind
# a pin-fitted mock, the parent's outline from CORE_UTILIZATION and the
# annealer: the flow the selection tables and the CoreMark/Joule power
# numbers came from. Dormant -- manual, and nothing in the baseline
# depends on it -- but kept so the power study can be reconnected without
# rebuilding what it measured. The table of arguments is in xiangshan.bzl.
xiangshan_flow(variant = "blocks")

# The planned parent: the blocks the macro selection tables named, each a
# real flow at the outline plan_floorplan.py drew with its pins on one
# side, the parent at the planned die. plan/ is generated (see
# .claude/commands/macro-selection.md, step 3); regenerate it, never edit it.
xiangshan_flow(
    name = "XSCore",
    plan = PLAN,
)

# The planned parent's synthesis: the blocks as blackboxes over the flat
# parent logic, where probe_pin_partners.tcl reads which block each block
# pin talks to (geometry only: run with GUI_TIMING=0).
odb_debug(
    name = "XSCore_synth_odb_debug",
    src = ":XSCore_synth",
)

# The placement gate of the planned parent: free sites and RUDY before
# CTS and global route spend their hours (/odb-debug).
odb_debug(
    name = "XSCore_place_odb_debug",
    src = ":XSCore_place",
)

# The planned blocks' synthesis netlists with timing: the time table's
# source. A block synthesised alone at the target period has no fanout
# phantom and probes in minutes; its worst boundary crossing sorts the
# cut (50 % error bars against global route, enough to sort by).
[
    odb_debug(
        name = block + "_synth_odb_debug",
        src = ":" + block + "_synth",
    )
    for block in PLAN["macros"].keys()
]

# Each planned block's own minimum clock period, which is the per block
# series of the KPI (README.md, kpi.json). At place the block has no clock
# tree yet, so its reg2reg slack is against an ideal clock; the parent's
# number is the one that carries a clock tree. Timing, so these load in
# minutes, not seconds.
[
    odb_debug(
        name = block + "_place_odb_debug",
        src = ":" + block + "_place",
    )
    for block in PLAN["macros"].keys()
]

grt_netlist(
    name = "cmj_xiangshan_grt_netlist",
    src = ":XSCore_blocks_grt",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# XiangShan is the core the per-unit breakdown is for: its modules are
# monomorphic, so unlike SERV's parameterized ones they should reach the
# ODB with their names intact, and its hierarchy maps onto the categories
# the literature reports.
stage_power_units(
    name = "cmj_xiangshan_grt_power_units",
    src = ":XSCore_blocks_grt",
    saif = "//test/coremark_joule/sim:xiangshan_rv64gc_saif",
    saif_scope = "TOP/cm_soc/inner/soc/core_with_l2/core",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

stage_power(
    name = "cmj_xiangshan_grt_power",
    src = ":XSCore_blocks_grt",
    saif = "//test/coremark_joule/sim:xiangshan_rv64gc_saif",
    saif_scope = "TOP/cm_soc/inner/soc/core_with_l2/core",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# Did the sixteen SRAMs reach the netlist as macros? The flow can detect a
# memory, write its views, list it in blackboxes.txt and synthesise it as
# flip-flops anyway, and nothing fails -- which is exactly what happened
# to every one of these before patches 0069 and 0070: memories.json held
# two entries, both declined, and the L1s were 1.2 Mbit of flops. The
# expected list is declared, so an empty blackboxes.txt fails here rather
# than passing vacuously. Every name is a firtool array_<depth>x<width>
# module; the four-row array_4x786 and the two-row queues stay flops by
# the macro floors, on purpose.
# Flat-design expectation. With BLOCKS in config.mk most of these banks
# are converted inside their block's flow, not the parent's; re-derive
# this list per flow from the first hierarchical synthesis.
CONVERTED_MEMORIES = [
    "array_128x138",
    "array_128x18",
    "array_128x192",
    "array_128x38",
    "array_128x48",
    "array_128x76",
    "array_256x46",
    "array_256x66",
    "array_256x8",
    "array_256x86",
    "array_256x88",
    "array_32x148",
    "array_512x17",
    "array_64x112",
    "array_64x114",
    "array_64x16",
]

genrule(
    name = "cmj_xiangshan_memories_applied",
    srcs = [":XSCore_blocks_synth"],
    outs = ["cmj_xiangshan_memories_applied.txt"],
    cmd = "files=$$(echo $(locations :XSCore_synth) | tr ' ' '\\n'); " +
          "$(execpath //test/coremark_joule/scripts:check_memories_applied) " +
          "$$(echo \"$$files\" | grep '/memories$$')/blackboxes.txt " +
          "$$(echo \"$$files\" | grep '/1_2_yosys.v$$') " +
          "--expect " + " ".join(CONVERTED_MEMORIES) + " > $@",
    tags = ["manual"],
    tools = ["//test/coremark_joule/scripts:check_memories_applied"],
)

# Whether the kept module boundaries survived into the ODB. Cheap, and
# the failure it catches is silent: the flow completes, the netlist is
# valid, and the breakdown simply comes back empty.
[
    hier_probe(
        name = "cmj_xiangshan_hier_" + stage,
        src = ":XSCore_blocks_" + stage,
        stage = stage,
    )
    for stage in [
        "synth",
        "grt",
    ]
]

# The measured side of the literature table (§4.9), at every stage the
# flow has reached: the standard-cell area and the gate count are the
# same from placement on, the period is only worth quoting at grt.
[
    physical_probe(
        name = "cmj_xiangshan_physical_" + stage,
        src = ":XSCore_blocks_" + stage,
        stage = stage,
    )
    for stage in [
        "place",
        "grt",
    ]
]

# What is big: leaf instances and area under every kept module, the
# input to choosing which blocks to harden as macros.
census_probe(
    name = "cmj_xiangshan_census",
    src = ":XSCore_blocks_synth",
)

# The whole core, flat, no blocks, every candidate macro boundary kept as a
# module in synthesis and in the ODB (OPENROAD_HIERARCHICAL): the lasting
# data the macro selection reads its timing from. A plain orfs_flow, the
# first target of the XiangShan BUILD outside the config.mk DSL. Synthesis
# only; 800 ps is the target period for a core meant to route at 1000 ps.
orfs_flow(
    name = "XSCore",
    arguments = {
        "ABC_AREA": "1",
        "AUTO_MEMORIES": "1",
        "OPENROAD_HIERARCHICAL": "1",
        "SKIP_EXTRACT_FA": "1",
        "SKIP_REPORT_METRICS": "1",
        "SYNTH_HIERARCHICAL": "1",
        "SYNTH_KEEP_MODULES": "Frontend Backend MemBlock CtrlBlock FusionDecoder NewLoadUnit PMP PMPChecker PTWFilter Uncache PMPChecker_8 PTWNewFilter Region DecodeStage SimpleDecodeChannel UopBufferCtrlDecoder VecRegionModule Bpu ICache DCacheWrapper L2TLBWrapper Rob Dispatch Rename MemCtrl Region_1 LsqWrapper IssueQueueAluCsrFenceLinkBrhNjmp IssueQueueAluDivBrhNjmp IssueQueueAluI2fBrhNjmp IssueQueueAluBkuVset IssueQueueAluMul IssueQueueLdu IssueQueueStaMou IssueQueueStaMou_1 IssueQueueStdMoud IssueQueueStdMoud_1 DataPath ExuBlock VectorDecodeChannel Sbuffer TLBNonBlock TLBNonBlock_1 TLBNonBlock_2 PrefetcherWrapper HPerfMonitor_3 Ifu Ftq IBuffer TLB IssuePipeVialuVfmaVfdivVidiv IssuePipeVialuVimacVmoveVfcvtVfma IssuePipeVialuVfma IssuePipeVialuVfma_1 VIDiv VFDivWrapper VFMacWrapper VCVTWrapper VectorCvt VIMacU IssueQueueVialuVimacVmoveVfcvtVfma IssueQueueVialuVfmaVfdivVidiv IssueQueueVialuVfma IssueQueueVialuVfma_1 IssueQueueVstd VectorFMAS2 MainBtbAlignBank MainBtbInternalBank WriteBuffer_4 Tage TageTable TageTable_1 TageTable_2 TageTable_3 TageTable_4 TageTable_5 TageTable_6 TageTable_7 Sc Sc_Anon_7 WriteBuffer_68 AheadBtb Phr MicroTage Ittage MissQueue MissEntry BankedDataArray L1ErrorMetaArray L1PrefetchSourceArray L1CohMetaArray L1FlagMetaArray MainPipe L1RefillLatencyArray PtwCache LLPTW PTW HPTW RenameBuffer VTypeBuffer RobEntryCell BusyTable BusyTable_1 RenameTableWrapper CompressUnit SSIT LFST IssueQueueFaluFmacFdiv ExuBlock_1 ExeUnitImp_10 ExeUnitImp_9 DataPath_1 IssueQueueFaluFmacFcvtFcmp IssueQueueFaluFmac LoadQueueReplay LoadQueueRAW LoadQueueRAR VirtualLoadQueue LoadQueueUncache StoreQueue PhysicalStoreQueue ForwardModule SqEntryCell SqForwardPipe VirtualStoreQueue AgeDetector_40 EntriesAluCsrFenceLinkBrhNjmp EntriesAluDivBrhNjmp EntriesAluI2fBrhNjmp EntriesAluBkuVset EntriesAluMul EntriesLdu EntriesStaMou EntriesStdMoud ExeUnitImp NewCSR SbufferData ResolveQueue",
        "SYNTH_NUM_PARTITIONS": "48",
    },
    last_stage = "synth",
    pdk = "//flow:asap7",
    sources = {
        "SDC_FILE": [":constraints_800ps.sdc"],
        "STRUCTURED_MEMORIES": [
            ":FpRegFilePart0.regfile",
            ":FpRegFilePart1.regfile",
            ":FpRegFilePart2.regfile",
            ":FpRegFilePart3.regfile",
            ":FtqEntryQueue.regfile",
            ":FtqMetaQueueCommit.regfile",
            ":FtqMetaQueueRedirect.regfile",
            ":FtqMetaQueueResolve.regfile",
            ":IntRegFile.regfile",
            ":RenameBufferFile.regfile",
            ":VfRegFile.regfile",
        ],
    },
    top = "XSCore",
    variant = "hier",
    verilog_files = ["//test/coremark_joule/xiangshan:xiangshan_flat.sv"],
)

odb_debug(
    name = "XSCore_hier_synth_odb_debug",
    src = ":XSCore_hier_synth",
)

# Every module of size kept, 245 of them with 1500 or more lines of
# generated Verilog, not a hand-written list of units: the boundaries the
# RTL already has, wherever they are. Same probe. (SYNTH_MINIMUM_KEEP_SIZE
# would do this by area, but the keep pass has no cost for the memory
# blackboxes AUTO_MEMORIES makes, so the list is explicit.)
orfs_flow(
    name = "XSCore",
    arguments = {
        "ABC_AREA": "1",
        "AUTO_MEMORIES": "1",
        "OPENROAD_HIERARCHICAL": "1",
        "SKIP_EXTRACT_FA": "1",
        "SKIP_REPORT_METRICS": "1",
        "SYNTH_HIERARCHICAL": "1",
        "SYNTH_KEEP_MODULES": "TLToAXI4 VectorDecodeChannel LoadQueueReplay TLFIFOFixer BusyTable_1 BusyTable CtrlBlock Rob Phr Sbuffer Dispatch TLBFA_1 VirtualStoreQueue L1ErrorMetaArray NCBTransactionQueue IssueQueueVialuVimacVmoveVfcvtVfma IssueQueueVialuVfmaVfdivVidiv IssueQueueVialuVfma IssueQueueVialuVfma_1 SSIT DCache VirtualLoadQueue TLBFA_3 NCB200 DecodeChannels_MOP8_UOP8_M2x8_M4x8_M8x8 CompressUnit RenameBufferFile SbufferData AheadBtb UopBufferCtrlDecoder MemBlock LFST Ifu BankedDataArray PtwCache L1PrefetchSourceArray TLBFA_2 Region L2TLB PhysicalStoreQueue Tage Backend Sc LoadQueueRAW MissQueue EntriesAluCsrFenceLinkBrhNjmp EntriesLdu EntriesAluI2fBrhNjmp EntriesAluDivBrhNjmp BloomFilter_Verification_Assert IBuffer NewCSR VTypeBuffer EntriesAluBkuVset TLBFA ResolveQueue MSHRCtl NCBTransactionAgeMatrix L1CohMetaArray L1FlagMetaArray FpRegFilePart0 FpRegFilePart1 FpRegFilePart2 FpRegFilePart3 EntriesAluMul IntRegFile Domain_1 LoadQueueRAR Domain NCB200_1 WriteBuffer_4 BypassShadowBuffer AgeDetector_40 InterruptFilter EntriesFaluFmacFcvtFcmp L1RefillLatencyArray BypassShadowBuffer_1 EntriesFaluFmacFdiv Frontend EntriesFaluFmac EntriesStaMou Slice NCBTransactionQueue_1 RenameTable_2 ICacheReplacer IssueQueueVstd Rename UopSelectModule_DecodeChannelOutput_MopCtrlBundle MainPipe BufferSelectModule_DecodeChannelOutput_MopCtrlBundle MutiLevelPrefetchFilter EntriesStdMoud NCBTransactionPayload ResponseUnit StdFreeList MEFreeList LoadQueueUncache Bpu MemUnit XSCore VfRegFile RenameTable_1 DataPath LLPTW TLDebugModuleInner RenameTable ICacheWayLookup RenameBuffer VecRegionModule RefillUnit NCBTransactionPayload_Verification_Assert LoadQueueReplay_Verification_Assert WriteBuffer_68 VpnTable FrontendTrigger Region_1 AXI4UserYanker_2 TLBNonBlock Ftq MemMisc DataPath_1 AXI4Deinterleaver Uncache LsqWrapper NCBTransactionPayload_1 CommitQueue PMP AXI4Xbar SqForwardPipe MainPipe_1 NCBTransactionAgeMatrix_1 PipeGroupConnect SimpleDecodeChannel NewLoadUnit Slice_1 PredChecker BypassNetwork_6 PTWFilterEntry BlockCipherModule RequestBuffer VectorFMAS2 SentUnit RequestArb PatternHistoryTable TwoLevelRRArbiter_18 DecodeStage AXI4Xbar_Verification_Assert FreeList_2 StdFreeList_1 TLPMA ForwardModule PTWFilterEntry_2 AXI4ToTL RegCacheTagModule XSTop FtTrainPipeline FreeList NCBOrderAddressCAM PrefetchFilter SinkC fpsqrt_r16_block NCBTransactionPayload_1_Verification_Assert MMIOBridge FusionDecoder FloatFMA TLBNonBlock_2 TIMER OpenNCB AXI4UserYanker DeltaPrefetchBuffer LoadQueue AXI4UserYanker_3 TLBNonBlock_1 CDPPrefetcher StreamBitVectorArray_Verification_Assert Directory RegCacheDataModule RasStack LqPAddrModule HPerfCounter_21 VecExcpDataMergeModule RegCacheAgeTimer RegCacheAgeDetector CoupledL2 AheadBtbReplacer IssueQueueAluI2fBrhNjmp IssueQueueAluCsrFenceLinkBrhNjmp OpenLLC TLPLIC RegCache IssueQueueAluDivBrhNjmp NCBUpstreamTXDAT StreamBitVectorArray RegCacheDataModule_Verification_Assert EnqEntry_4 L2Top IntRFBankReadArbiter SnoopUnit EnqEntry EnqEntry_2 PMPChecker_8 EnqEntry_6 PTWFilter RegCacheTagTable MicroBtb MissEntry VFEX0 EnqEntry_8 OffsetScoreTable_1 ReplacerState_4 VectorFloatDividerR64 ExuBlock Misc CommonHR SplittedSRAM_1 IssueQueueAluBkuVset WriteBuffer_12 StoreQueue ExceptionGen AgeDetector_33 MSHR FreeList_1 TwoLevelRRArbiter_12 IssueQueueAluMul PMPChecker VectorFMA LqPAddrModule_1 NCBUpstreamRXREQ ICache WritebackQueue PTW ActiveGenerationTable IssueQueueLdu EnqEntry_26 StdFreeList_2 IssueQueueFaluFmacFcvtFcmp EnqEntry_28 AXI4Deinterleaver_Verification_Assert EnqEntry_32 MicroTage PTWFilterEntry_1 OverwriteQueue_1 XSTile OthersEntry_38 OthersEntry_6",
        "SYNTH_NUM_PARTITIONS": "48",
    },
    last_stage = "synth",
    pdk = "//flow:asap7",
    sources = {
        "SDC_FILE": [":constraints_800ps.sdc"],
        "STRUCTURED_MEMORIES": [
            "FpRegFilePart0.regfile",
            ":FpRegFilePart1.regfile",
            ":FpRegFilePart2.regfile",
            ":FpRegFilePart3.regfile",
            ":FtqEntryQueue.regfile",
            ":FtqMetaQueueCommit.regfile",
            ":FtqMetaQueueRedirect.regfile",
            ":FtqMetaQueueResolve.regfile",
            ":IntRegFile.regfile",
            ":RenameBufferFile.regfile",
            ":VfRegFile.regfile",
        ],
    },
    top = "XSCore",
    variant = "hier_all",
    verilog_files = ["//test/coremark_joule/xiangshan:xiangshan_flat.sv"],
)

odb_debug(
    name = "XSCore_hier_all_synth_odb_debug",
    src = ":XSCore_hier_all_synth",
)
