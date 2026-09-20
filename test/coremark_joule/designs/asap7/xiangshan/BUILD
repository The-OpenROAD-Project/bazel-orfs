load("@bazel-orfs//:openroad.bzl", "odb_debug", "orfs_flow")
load("//test/coremark_joule/flow:power.bzl", "census_probe", "grt_netlist", "hier_probe", "physical_probe", "stage_power", "stage_power_units")
load(":xiangshan.bzl", "xiangshan_flow")

exports_files(["constraints.sdc"])

# The parent and its blocks: plain orfs_flow() targets, the table of
# arguments in xiangshan.bzl. See there.
xiangshan_flow()

grt_netlist(
    name = "cmj_xiangshan_grt_netlist",
    src = ":XSCore_grt",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# XiangShan is the core the per-unit breakdown is for: its modules are
# monomorphic, so unlike SERV's parameterized ones they should reach the
# ODB with their names intact, and its hierarchy maps onto the categories
# the literature reports.
stage_power_units(
    name = "cmj_xiangshan_grt_power_units",
    src = ":XSCore_grt",
    saif = "//test/coremark_joule/sim:xiangshan_rv64gc_saif",
    saif_scope = "TOP/cm_soc/inner/soc/core_with_l2/core",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

stage_power(
    name = "cmj_xiangshan_grt_power",
    src = ":XSCore_grt",
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
    srcs = [":XSCore_synth"],
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
        src = ":XSCore_" + stage,
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
        src = ":XSCore_" + stage,
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
    src = ":XSCore_synth",
)

# The whole core, flat, no blocks, every candidate macro boundary kept as a
# module in synthesis and in the ODB (OPENROAD_HIERARCHICAL): the lasting
# data the macro selection reads its timing from. A plain orfs_flow, the
# first target of the XiangShan BUILD outside the config.mk DSL. Synthesis
# only; 800 ps is the target period for a core meant to route at 1000 ps.
orfs_flow(
    name = "XSCore_hier",
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
    verilog_files = ["//test/coremark_joule/xiangshan:xiangshan_flat.sv"],
)

odb_debug(
    name = "XSCore_hier_synth_odb_debug",
    src = ":XSCore_hier_synth",
)

# Every module above a size threshold kept, not a hand-written list: the
# boundaries the RTL already has, wherever they are. Same probe.
orfs_flow(
    name = "XSCore_hier_all",
    arguments = {
        "ABC_AREA": "1",
        "AUTO_MEMORIES": "1",
        "SYNTH_MINIMUM_KEEP_SIZE": "2000",
        "OPENROAD_HIERARCHICAL": "1",
        "SKIP_EXTRACT_FA": "1",
        "SKIP_REPORT_METRICS": "1",
        "SYNTH_HIERARCHICAL": "1",
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
    verilog_files = ["//test/coremark_joule/xiangshan:xiangshan_flat.sv"],
)

odb_debug(
    name = "XSCore_hier_all_synth_odb_debug",
    src = ":XSCore_hier_all_synth",
)
