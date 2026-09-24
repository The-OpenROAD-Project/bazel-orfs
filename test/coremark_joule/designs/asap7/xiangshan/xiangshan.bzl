"""XiangShan on asap7 as plain orfs_flow() targets.

Generated once from the design table the config.mk DSL produced (the
parent and its 34 blocks), then maintained by hand: the study outgrew the
DSL, and a macro set chosen by interface rather than by synthesis time is
edited here as data. Every block is its own flow abstracted at place with
a pin-fitted mock for the parent; the parent's synthesis blackboxes the
blocks by name from their abstracts.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

# Read by anneal_in_flow.tcl, not by ORFS: bypass the variables.yaml
# validator, and scoped to the floorplan so a knob edit re-runs the
# floorplan and not the synthesis before it.
XS_USER_ARGUMENTS = ["ANNEAL_SEED", "ANNEAL_DEPTH", "ANNEAL_MIN_CLUSTER", "ANNEAL_CHANNEL_UM", "ANNEAL_BLOCK_GAP_UM", "ANNEAL_FILL", "ANNEAL_STRAP_PITCH_UM", "ANNEAL_STRAP_OFFSET_UM", "ANNEAL_STRAP_PAIR_UM", "ANNEAL_CHANNEL_CHECK", "ANNEAL_CHANNEL_AUTO", "ANNEAL_CHANNEL_MIN_UM"]
XS_USER_SOURCES = ["ANNEAL_DUMP_TCL", "ANNEAL_PY"]
XS_USER_STAGES = {v: ["floorplan"] for v in XS_USER_ARGUMENTS + XS_USER_SOURCES}

# The flat core. Elaborated without Chisel's verification layer (see the
# generator's firtool arguments), so slang reads it with the hierarchy kept.
XS_VERILOG = ["//test/coremark_joule/xiangshan:xiangshan_flat.sv"]

XS_PARENT = {
    "arguments": {
        "ABC_AREA": "1",
        "AUTO_MEMORIES": "1",
        "CORE_MARGIN": "2",
        "CORE_UTILIZATION": "18",
        "DETAIL_PLACEMENT_ARGS": "-use_diamond_legalizer -max_displacement {450 450}",
        "ENABLE_DPO": "0",
        "GPL_ROUTABILITY_DRIVEN": "0",
        "GPL_TIMING_DRIVEN": "0",
        "MACRO_PLACE_HALO": "2 2",
        "OPENROAD_HIERARCHICAL": "1",
        "PLACE_DENSITY": "0.65",
        "REMOVE_ABC_BUFFERS": "1",
        "SKIP_CTS_REPAIR_TIMING": "1",
        "SKIP_EXTRACT_FA": "1",
        "SKIP_INCREMENTAL_REPAIR": "1",
        "SKIP_LAST_GASP": "1",
        "SKIP_REPORT_METRICS": "1",
        "SYNTH_HIERARCHICAL": "1",
        "SYNTH_KEEP_MODULES": "Frontend                                  Backend                                  MemBlock                                  CtrlBlock                                  FusionDecoder                                  NewLoadUnit                                  PMP                                  PMPChecker                                  PTWFilter                                  Uncache                                  PMPChecker_8                                  PTWNewFilter                                  Region                                  DecodeStage                                  SimpleDecodeChannel                                  UopBufferCtrlDecoder",
        "SYNTH_NUM_PARTITIONS": "16",
        "TNS_END_PERCENT": "1",
    },
    "user_arguments": {
        "ANNEAL_BLOCK_GAP_UM": "54.0",
        "ANNEAL_CHANNEL_AUTO": "0",
        "ANNEAL_CHANNEL_CHECK": "warn",
        "ANNEAL_CHANNEL_MIN_UM": "40",
        "ANNEAL_CHANNEL_UM": "4.0",
        "ANNEAL_DEPTH": "3",
        "ANNEAL_FILL": "0.5",
        "ANNEAL_MIN_CLUSTER": "1",
        "ANNEAL_SEED": "1",
        "ANNEAL_STRAP_OFFSET_UM": "1.5",
        "ANNEAL_STRAP_PAIR_UM": "0.312",
        "ANNEAL_STRAP_PITCH_UM": "2.16",
    },
    "user_sources": {
        "ANNEAL_DUMP_TCL": ["//test/coremark_joule/flow/macro_anneal:dump_macros.tcl"],
        "ANNEAL_PY": ["//test/coremark_joule/flow/macro_anneal:macro_anneal.py"],
    },
    "sources": {
        "MACRO_PLACEMENT_TCL": ["//test/coremark_joule/designs/asap7/xiangshan:anneal_in_flow.tcl"],
        "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCKS_grid_strategy.tcl"],
        "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
    },
}

# Block name -> its flow's arguments and sources. A block reads whichever
# annealer knobs its own settings name.
# In the order BLOCKS listed them; the parent's macro list follows it.
XS_BLOCK_ORDER = ["VecRegionModule", "Bpu", "ICache", "DCacheWrapper", "L2TLBWrapper", "Rob", "Dispatch", "Rename", "MemCtrl", "Region_1", "LsqWrapper", "IssueQueueAluCsrFenceLinkBrhNjmp", "IssueQueueAluDivBrhNjmp", "IssueQueueAluI2fBrhNjmp", "IssueQueueAluBkuVset", "IssueQueueAluMul", "IssueQueueLdu", "IssueQueueStaMou", "IssueQueueStaMou_1", "IssueQueueStdMoud", "IssueQueueStdMoud_1", "DataPath", "ExuBlock", "VectorDecodeChannel", "Sbuffer", "TLBNonBlock", "TLBNonBlock_1", "TLBNonBlock_2", "PrefetcherWrapper", "HPerfMonitor_3", "Ifu", "Ftq", "IBuffer", "TLB"]

XS_BLOCKS = {
    "Bpu": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "MainBtbAlignBank                                  MainBtbInternalBank                                  WriteBuffer_4                                  Tage                                  TageTable                                  TageTable_1                                  TageTable_2                                  TageTable_3                                  TageTable_4                                  TageTable_5                                  TageTable_6                                  TageTable_7                                  Sc                                  Sc_Anon_7                                  WriteBuffer_68                                  AheadBtb                                  Phr                                  MicroTage                                  Ittage",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {
            "ANNEAL_BLOCK_GAP_UM": "10.8",
            "ANNEAL_CHANNEL_UM": "4.0",
            "ANNEAL_DEPTH": "3",
            "ANNEAL_FILL": "0.5",
            "ANNEAL_MIN_CLUSTER": "1",
            "ANNEAL_SEED": "1",
            "ANNEAL_STRAP_OFFSET_UM": "0.3",
            "ANNEAL_STRAP_PAIR_UM": "0.312",
            "ANNEAL_STRAP_PITCH_UM": "5.4",
        },
        "user_sources": {
            "ANNEAL_DUMP_TCL": ["//test/coremark_joule/flow/macro_anneal:dump_macros.tcl"],
            "ANNEAL_PY": ["//test/coremark_joule/flow/macro_anneal:macro_anneal.py"],
        },
        "sources": {
            "MACRO_PLACEMENT_TCL": ["//test/coremark_joule/designs/asap7/xiangshan:anneal_in_flow.tcl"],
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "DCacheWrapper": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "MissQueue                                  MissEntry                                  BankedDataArray                                  L1ErrorMetaArray                                  L1PrefetchSourceArray                                  L1CohMetaArray                                  L1FlagMetaArray                                  MainPipe                                  L1RefillLatencyArray",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "DataPath": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "0",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
            "STRUCTURED_MEMORIES": ["//test/coremark_joule/designs/asap7/xiangshan:IntRegFile.regfile"],
        },
    },
    "Dispatch": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "25",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "BusyTable                                  BusyTable_1",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "ExuBlock": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "ExeUnitImp                                  NewCSR",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "Ftq": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "ResolveQueue",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
            "STRUCTURED_MEMORIES": ["//test/coremark_joule/designs/asap7/xiangshan:FtqEntryQueue.regfile", "//test/coremark_joule/designs/asap7/xiangshan:FtqMetaQueueRedirect.regfile", "//test/coremark_joule/designs/asap7/xiangshan:FtqMetaQueueResolve.regfile", "//test/coremark_joule/designs/asap7/xiangshan:FtqMetaQueueCommit.regfile"],
        },
    },
    "HPerfMonitor_3": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "0",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "IBuffer": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "0",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "ICache": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "0",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "Ifu": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "0",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "IssueQueueAluBkuVset": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "EntriesAluBkuVset",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "IssueQueueAluCsrFenceLinkBrhNjmp": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "EntriesAluCsrFenceLinkBrhNjmp",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "IssueQueueAluDivBrhNjmp": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "EntriesAluDivBrhNjmp",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "IssueQueueAluI2fBrhNjmp": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "EntriesAluI2fBrhNjmp",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "IssueQueueAluMul": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "EntriesAluMul",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "IssueQueueLdu": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "EntriesLdu",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "IssueQueueStaMou": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "EntriesStaMou",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "IssueQueueStaMou_1": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "EntriesStaMou",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "IssueQueueStdMoud": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "EntriesStdMoud",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "IssueQueueStdMoud_1": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "EntriesStdMoud",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "L2TLBWrapper": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "PtwCache                                  LLPTW                                  PMP                                  PMPChecker                                  PTW                                  HPTW",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "LsqWrapper": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "LoadQueueReplay                                  LoadQueueRAW                                  LoadQueueRAR                                  VirtualLoadQueue                                  LoadQueueUncache                                  StoreQueue                                  PhysicalStoreQueue                                  ForwardModule                                  SqEntryCell                                  SqForwardPipe                                  VirtualStoreQueue                                  AgeDetector_40",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "MemCtrl": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "SSIT                                  LFST",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "PrefetcherWrapper": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "0",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "Region_1": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "IssueQueueFaluFmacFdiv                                  ExuBlock_1                                  ExeUnitImp_10                                  ExeUnitImp_9                                  DataPath_1                                  IssueQueueFaluFmacFcvtFcmp                                  IssueQueueFaluFmac",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
            "STRUCTURED_MEMORIES": ["//test/coremark_joule/designs/asap7/xiangshan:FpRegFilePart0.regfile", "//test/coremark_joule/designs/asap7/xiangshan:FpRegFilePart1.regfile", "//test/coremark_joule/designs/asap7/xiangshan:FpRegFilePart2.regfile", "//test/coremark_joule/designs/asap7/xiangshan:FpRegFilePart3.regfile"],
        },
    },
    "Rename": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "RenameTableWrapper                                  CompressUnit",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "Rob": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "RenameBuffer                                  VTypeBuffer                                  RobEntryCell",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
            "STRUCTURED_MEMORIES": ["//test/coremark_joule/designs/asap7/xiangshan:RenameBufferFile.regfile", "//test/coremark_joule/designs/asap7/xiangshan:RobEntryFile.regfile"],
        },
    },
    "Sbuffer": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "SbufferData",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "TLB": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "0",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "TLBNonBlock": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "0",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "TLBNonBlock_1": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "0",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "TLBNonBlock_2": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "0",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
    "VecRegionModule": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "IssuePipeVialuVfmaVfdivVidiv                                  IssuePipeVialuVimacVmoveVfcvtVfma                                  IssuePipeVialuVfma                                  IssuePipeVialuVfma_1                                  VIDiv                                  VFDivWrapper                                  VFMacWrapper                                  VCVTWrapper                                  VectorCvt                                  VIMacU                                  IssueQueueVialuVimacVmoveVfcvtVfma                                  IssueQueueVialuVfmaVfdivVidiv                                  IssueQueueVialuVfma                                  IssueQueueVialuVfma_1                                  IssueQueueVstd                                  VectorFMAS2",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
            "STRUCTURED_MEMORIES": ["//test/coremark_joule/designs/asap7/xiangshan:VfRegFile.regfile"],
        },
    },
    "VectorDecodeChannel": {
        "arguments": {
            "ABC_AREA": "1",
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "MACRO_PLACE_HALO": "2 2",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "REMOVE_ABC_BUFFERS": "1",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "0",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
        },
    },
}

def _user_stages(user_arguments, user_sources):
    return {v: s for v, s in XS_USER_STAGES.items() if v in user_arguments or v in user_sources}

# A block the plan names that the table above does not: the Bpu flow's
# settings without its keep list (AUTO_MEMORIES, the annealer for the
# memory banks inside, pins on two layers per direction).
XS_BLOCK_DEFAULT = dict(XS_BLOCKS["Bpu"], arguments = {k: v for k, v in XS_BLOCKS["Bpu"]["arguments"].items() if k != "SYNTH_KEEP_MODULES"})

# Outline knobs a planned flow replaces with DIE_AREA/CORE_AREA, and the
# legaliser window the parent no longer needs once the channels are planned.
# SKIP_REPORT_METRICS stays on: report_metrics on a 3.7 M-instance parent
# runs for an hour per stage; slack is read from the stage ODB with
# odb-debug in seconds instead.
_PLAN_DROPS = ["CORE_UTILIZATION", "CORE_ASPECT_RATIO", "CORE_MARGIN", "DETAIL_PLACEMENT_ARGS"]

def _structured_memories(own_sources, keep, blocks):
    """The generated register files a planned flow hardens: its own, plus
    those of every block of the old table whose module it now keeps (the
    Ftq queues inside Frontend, the int register file and the ROB's files
    in the parent), each once."""
    out = list(own_sources.get("STRUCTURED_MEMORIES", []))
    for k in [k for k in keep.split(" ") if k]:
        for m in blocks.get(k, {}).get("sources", {}).get("STRUCTURED_MEMORIES", []):
            if m not in out:
                out.append(m)
    return out

def _planned_block(cfg, entry, plan_dir, block, blocks):
    """A block flow's arguments and sources under the plan: planned outline,
    every pin on the planned side, the parent's target period."""
    arguments = {k: v for k, v in cfg["arguments"].items() if k not in _PLAN_DROPS}
    arguments["DIE_AREA"] = entry["DIE_AREA"]
    arguments["CORE_AREA"] = entry["CORE_AREA"]

    # the block is abstracted at cts: build its tree, do not repair its
    # timing there (the parent skips it too; margin first)
    arguments["SKIP_CTS_REPAIR_TIMING"] = "1"
    if "SYNTH_KEEP_MODULES" in entry:
        arguments["SYNTH_KEEP_MODULES"] = entry["SYNTH_KEEP_MODULES"]
    sources = dict(cfg["sources"])
    mems = _structured_memories(cfg["sources"], entry.get("SYNTH_KEEP_MODULES", ""), blocks)
    if mems:
        sources["STRUCTURED_MEMORIES"] = mems
    sources["IO_CONSTRAINTS"] = [":%s/%s_pins.tcl" % (plan_dir, block)]
    sources["SDC_FILE"] = ["//test/coremark_joule/designs/asap7/xiangshan:constraints_800ps.sdc"]
    return arguments, sources

def xiangshan_flow(name = "XSCore", blocks = XS_BLOCKS, parent = XS_PARENT, tags = ["manual"], plan = None, plan_dir = "plan", variant = None):
    """The blocks, each abstracted, then the parent.

    Without a plan: every block in `blocks` with a pin-fitted mock for the
    parent, abstracted at place, the parent's outline from
    CORE_UTILIZATION and the annealer.
    With a plan (the PLAN dict plan_floorplan.py --emit wrote to
    plan_dir/plan.bzl): only the plan's blocks, each a real flow at the
    planned outline with its pins on the planned side and no mock; the
    parent at the planned die with plan_dir/place_macros.tcl placing the
    blocks R0 where the plan put them. `variant` keeps the two apart.
    The planned blocks are abstracted at cts, so the parent's CTS and
    timing see each block's clock pin as its tree's root buffer and its
    insertion delay, not the whole unbuffered clock net (entry 17 of
    ideas/xiangshan-timing.md); the parent's synthesis, floorplan and place
    read the place-stage abstract the flow emits beside it.
    """
    if plan == None:
        for block, cfg in blocks.items():
            orfs_flow(
                name = block,
                abstract_stage = "place",
                arguments = cfg["arguments"],
                mock_area = "pins",
                pdk = "//flow:asap7",
                sources = cfg["sources"],
                tags = tags,
                user_arguments = cfg["user_arguments"],
                user_sources = cfg["user_sources"],
                user_stages = _user_stages(cfg["user_arguments"], cfg["user_sources"]),
                variant = variant,
                verilog_files = XS_VERILOG,
            )
        macros = [b for b in XS_BLOCK_ORDER if b in blocks]
        arguments = parent["arguments"]
        sources = parent["sources"]
        user_arguments = parent["user_arguments"]
        user_sources = parent["user_sources"]
    else:
        macros = sorted(plan["macros"].keys())
        for block in macros:
            cfg = blocks.get(block, XS_BLOCK_DEFAULT)
            arguments, sources = _planned_block(cfg, plan["macros"][block], plan_dir, block, blocks)
            orfs_flow(
                name = block,
                abstract_stage = "cts",
                arguments = arguments,
                pdk = "//flow:asap7",
                sources = sources,
                tags = tags,
                user_arguments = cfg["user_arguments"],
                user_sources = cfg["user_sources"],
                user_stages = _user_stages(cfg["user_arguments"], cfg["user_sources"]),
                variant = variant,
                verilog_files = XS_VERILOG,
            )
        arguments = {k: v for k, v in parent["arguments"].items() if k not in _PLAN_DROPS}
        arguments["DIE_AREA"] = plan["parent"]["DIE_AREA"]
        arguments["CORE_AREA"] = plan["parent"]["CORE_AREA"]

        # the diamond search: the negotiation legalizer ran past 5 h
        # after CTS on take 19 (ideas, entry 5). At its default 27 um
        # window the diamond placed all but one of 3.57 M cells in 76 min
        # (take 20); 100 um (microns, not sites) is for that one cell,
        # and patch 0004's window check answers in a second here
        arguments["DETAIL_PLACEMENT_ARGS"] = "-use_diamond_legalizer -max_displacement {100 100}"

        # Take 23's route-0: 78 percent of the overflow in the parent's own
        # wiring above two of the blocks at 60 percent cell density, with
        # empty rows above the other two; the die has the room, the placer
        # is told to use it. The layer adjustment is the value the tile
        # flows settled on (OpenROAD's GRT-0704 hint), 9 percent more
        # capacity on every layer than the platform's 0.25.
        arguments["PLACE_DENSITY"] = "0.5"
        arguments["ROUTING_LAYER_ADJUSTMENT"] = "0.18"

        # The rest of the measured configuration, in the flow rather than in
        # a shell around it. A deploy tree carries only its own stage's
        # variables, so a workbench that ran later stages from the floorplan
        # tree ran them on the platform's defaults -- M7 and a 0.25
        # adjustment -- and measured something the build never asked for.
        arguments["MAX_ROUTING_LAYER"] = "M9"
        arguments["MIN_ROUTING_LAYER"] = "M2"
        arguments["IO_PLACER_H"] = "M2 M4"
        arguments["IO_PLACER_V"] = "M3 M5"
        arguments["PLACE_PINS_ARGS"] = "-annealing"

        # Clock tree synthesis pads every register's clock path out to the
        # insertion delay of the block macros, whose abstracts are written
        # at their place stage and so carry a whole unbuffered clock net:
        # 49 736 delay buffers on the parent, six times its leaf buffers,
        # and 2.6 hours of legalisation to seat them. A flow that is not yet
        # asking for skew against the blocks does not want them. ORFS's own
        # arguments are repeated because CTS_ARGS replaces them wholesale.
        arguments["CTS_ARGS"] = "-sink_clustering_enable -repair_clock_nets -no_insertion_delay"

        # Zero iterations with congestion allowed: the route reports what it
        # would have to route and stops, which is the number this baseline
        # tracks and the map the GUI shows. One maze iteration on this die's
        # gcell grid takes hours, so the iterating route is what the work
        # ahead is for, not what the reference runs.
        arguments["GLOBAL_ROUTE_ARGS"] = "-congestion_iterations 0 -allow_congestion -verbose"

        # Global route stops in pin access on exactly one pin per hardened
        # block (DRT-0073). Skipped so the stage produces its congestion
        # map; carried ORFS patch 0085 has the detail and retires with the
        # bug. A five-second reproducer is in test/planned_parent.
        arguments["SKIP_PIN_ACCESS"] = "1"
        if "SYNTH_KEEP_MODULES" in plan["parent"]:
            # what the blocks swallowed no longer exists in the parent
            arguments["SYNTH_KEEP_MODULES"] = plan["parent"]["SYNTH_KEEP_MODULES"]
        sources = dict(parent["sources"])

        # the memories of what the parent still holds; a hardened block's
        # are the block's own
        parent_keep = " ".join([k for k in arguments.get("SYNTH_KEEP_MODULES", "").split(" ") if k and k not in macros])
        mems = _structured_memories(parent["sources"], parent_keep, blocks)
        if mems:
            sources["STRUCTURED_MEMORIES"] = mems
        sources["MACRO_PLACEMENT_TCL"] = [":%s/place_macros.tcl" % plan_dir]
        if plan["parent"].get("netlists"):
            # the generated arrays dropped FIRM into the parent at floorplan
            # (STRUCTURED_MEMORIES in mode netlist, patch 0078)
            sources["STRUCTURED_PLACEMENT"] = [":%s/netlists.txt" % plan_dir]
        sources["SDC_FILE"] = ["//test/coremark_joule/designs/asap7/xiangshan:constraints_800ps.sdc"]
        user_arguments = {}
        user_sources = {}
    suffix = "_" + variant if variant else ""
    orfs_flow(
        name = name,
        arguments = arguments,
        macros = [":%s%s_generate_abstract" % (b, suffix) for b in macros],
        pdk = "//flow:asap7",
        sources = sources,
        tags = tags,
        user_arguments = user_arguments,
        user_sources = user_sources,
        user_stages = _user_stages(user_arguments, user_sources),
        variant = variant,
        verilog_files = XS_VERILOG,
        visibility = ["//visibility:public"],
    )
