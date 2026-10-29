"""XiangShan on asap7 as plain orfs_flow() targets.

Generated once from the design table the config.mk DSL produced (the
parent and its 34 blocks), then maintained by hand: the study outgrew the
DSL, and a macro set chosen by interface rather than by synthesis time is
edited here as data. The parent is XSTile, the core and its L2; every
planned block is its own flow implemented through global route and
abstracted there, and the parent's synthesis blackboxes the blocks by
name from their abstracts.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_headroom", "orfs_run")

# Read by anneal_in_flow.tcl, not by ORFS: bypass the variables.yaml
# validator, and scoped to the floorplan so a knob edit re-runs the
# floorplan and not the synthesis before it.
XS_USER_ARGUMENTS = ["ANNEAL_SEED", "ANNEAL_DEPTH", "ANNEAL_MIN_CLUSTER", "ANNEAL_CHANNEL_UM", "ANNEAL_BLOCK_GAP_UM", "ANNEAL_FILL", "ANNEAL_STRAP_PITCH_UM", "ANNEAL_STRAP_OFFSET_UM", "ANNEAL_STRAP_PAIR_UM", "ANNEAL_CHANNEL_CHECK", "ANNEAL_CHANNEL_AUTO", "ANNEAL_CHANNEL_MIN_UM"]
XS_USER_SOURCES = ["ANNEAL_DUMP_TCL", "ANNEAL_PY"]

# XiangShan's ClockGate onto ASAP7's ICG cell in every flow, the parent's
# and every block's: the RTL is one core. The hook's script is named by
# sandbox path; XS_ICG_MAP is what stages it and the template, and is
# never handed to the frontend (the template defines a second ClockGate).
# Synthesis only: test/xs_clockgate checks the mapping.
XS_ICG_USER_ARGUMENTS = {
    "SYNTH_POST_HIERARCHY_SCRIPTS": "test/coremark_joule/designs/asap7/xiangshan/xs_icg.ys",
}
XS_ICG_USER_SOURCES = {
    "XS_ICG_MAP": [
        "//test/coremark_joule/designs/asap7/xiangshan:xs_icg.ys",
        "//test/coremark_joule/designs/asap7/xiangshan:xs_icg_map.v",
    ],
}
XS_USER_STAGES = {v: ["floorplan"] for v in XS_USER_ARGUMENTS + XS_USER_SOURCES} | {
    v: ["synth"]
    for v in list(XS_ICG_USER_ARGUMENTS) + list(XS_ICG_USER_SOURCES) + ["XS_FOLD_MODULES"]
}

# The flat core. Elaborated without Chisel's verification layer (see the
# generator's firtool arguments), so slang reads it with the hierarchy kept.
# After the surgery that folds the constants XiangShan ties into the
# modules this flow keeps (surgery/xs_surgery.py, surgery/manifest.json).
XS_VERILOG = ["//test/coremark_joule/designs/asap7/xiangshan/surgery:xiangshan_surgered.sv"]

# The modules the arrays front end replaces (arrays/: each found, extracted
# as one entry cell instanced per entry, and proven against the module it
# came from), per part of the plan that holds them; "parent" is the tile's
# own. Those parts read the surgered core with the extractions in place
# (arrays:xiangshan_extracted), keep each entry cell, and fold slang's
# per-instance copies of it onto one module (fold_entries.tcl), so
# synthesis maps it once; every other part reads XS_VERILOG. "absorbed"
# are the plan's kept modules an extraction flattened into itself
# (SqForwardPipe in PhysicalStoreQueue, the Rob's entry cells): they no
# longer exist to be kept.
XS_EXTRACTED = {
    "MemBlock": {
        "absorbed": ["SqForwardPipe"],
        "modules": ["LoadQueueRAR", "LoadQueueReplay", "PhysicalStoreQueue", "TLBFA_1", "VirtualStoreQueue"],
    },
    "parent": {
        "absorbed": ["RobEntryCell"],
        "modules": ["Rob"],
    },
}
XS_EXTRACTED_VERILOG = ["//test/coremark_joule/designs/asap7/xiangshan/arrays:xiangshan_extracted.sv"]

def _extracted(part, arguments, sources, user_arguments):
    """A part's Verilog, arguments, sources and user arguments with its
    extracted modules (XS_EXTRACTED) in place; unchanged for a part
    without any."""
    if part not in XS_EXTRACTED:
        return XS_VERILOG, arguments, sources, user_arguments
    entries = ["%sEntry" % m for m in XS_EXTRACTED[part]["modules"]]
    keep = [k for k in arguments.get("SYNTH_KEEP_MODULES", "").split(" ") if k and k not in XS_EXTRACTED[part]["absorbed"]]
    arguments = dict(arguments, SYNTH_KEEP_MODULES = " ".join(keep + entries))
    sources = dict(sources, SYNTH_CANONICALIZE_TCL = ["//test/coremark_joule/designs/asap7/xiangshan:fold_entries.tcl"])
    user_arguments = dict(user_arguments, XS_FOLD_MODULES = " ".join(entries))
    return XS_EXTRACTED_VERILOG, arguments, sources, user_arguments

XS_PARENT = {
    "arguments": {
        "AUTO_MEMORIES": "1",
        "CORE_MARGIN": "2",
        "CORE_UTILIZATION": "18",
        "DETAIL_PLACEMENT_ARGS": "-use_diamond_legalizer -max_displacement {450 450}",
        "ENABLE_DPO": "0",
        # timing-driven global placement keeps its repair_design changes only
        # below this overflow. At the default, 1, the parent kept the buffer
        # chains of its first repair, made at overflow 0.63, and they zig-zagged
        # as the cells moved; at 0 the buffers are made on the final placement
        "GPL_KEEP_OVERFLOW": "0",
        "RTLMP_MIN_CHANNEL_SIZE": "4 4",
        "OPENROAD_HIERARCHICAL": "1",
        "PLACE_DENSITY": "0.65",
        # the study stops at global route: no detailed route to protect, and
        # the check's wire for every net sets the stage's peak memory
        "SKIP_ANTENNA_REPAIR": "1",
        "SKIP_EXTRACT_FA": "1",
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
XS_BLOCKS = {
    "Bpu": {
        "arguments": {
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES_REGFILES": ["//test/coremark_joule/designs/asap7/xiangshan:IntRegFile.regfile"],
        },
    },
    "Dispatch": {
        "arguments": {
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "25",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES_REGFILES": ["//test/coremark_joule/designs/asap7/xiangshan:FtqEntryQueue.regfile", "//test/coremark_joule/designs/asap7/xiangshan:FtqMetaQueueRedirect.regfile", "//test/coremark_joule/designs/asap7/xiangshan:FtqMetaQueueResolve.regfile", "//test/coremark_joule/designs/asap7/xiangshan:FtqMetaQueueCommit.regfile"],
        },
    },
    "HPerfMonitor_3": {
        "arguments": {
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "LoadQueueReplay                                  LoadQueueRAW                                  LoadQueueRAR                                  VirtualLoadQueue                                  LoadQueueUncache                                  StoreQueue                                  PhysicalStoreQueue                                  ForwardModule                                  SqEntryCell                                  SqForwardPipe                                  VirtualStoreQueue                                  AgeDetector_36",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
    "FltRegionModule": {
        "arguments": {
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "FMulFlt FDivSqrtFlt IssuePipeFaluFmulFcvtFcmp IssuePipeFaluFmulFdiv IssuePipeFaluFmulFdiv_1 IssuePipeFaluFmul IssueQueueFaluFmulFcvtFcmp IssueQueueFaluFmulFdiv IssueQueueFaluFmulFdiv_1 IssueQueueFaluFmul",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
            "AUTO_MEMORIES_REGFILES": ["//test/coremark_joule/designs/asap7/xiangshan:FpRegFile.regfile"],
        },
    },
    "Rename": {
        "arguments": {
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES_REGFILES": ["//test/coremark_joule/designs/asap7/xiangshan:RenameBufferFile.regfile", "//test/coremark_joule/designs/asap7/xiangshan:RobEntryFile.regfile"],
        },
    },
    "Sbuffer": {
        "arguments": {
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
            "SKIP_EXTRACT_FA": "1",
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "VFDivWrapper VIDiv VIMacU IssuePipeVialuVimacVmoveVfcvtVfmac IssuePipeVialuVidivVfmacVfdiv IssuePipeVialu IssuePipeVialu_1 VectorCvt IssueQueueVialuVimacVmoveVfcvtVfmac IssueQueueVialu IssueQueueVialu_1 IssueQueueVialuVidivVfmacVfdiv VFMacWrapper",
            "TNS_END_PERCENT": "1",
        },
        "user_arguments": {},
        "user_sources": {},
        "sources": {
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
            "AUTO_MEMORIES_REGFILES": ["//test/coremark_joule/designs/asap7/xiangshan:VfRegFile.regfile"],
        },
    },
    "VectorDecodeChannel": {
        "arguments": {
            "AUTO_MEMORIES": "1",
            "CORE_ASPECT_RATIO": "1",
            "CORE_UTILIZATION": "40",
            "ENABLE_DPO": "0",
            "IO_PLACER_H": "M2 M4",
            "IO_PLACER_V": "M3 M5",
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
            "OPENROAD_HIERARCHICAL": "0",
            "PLACE_DENSITY": "0.6",
            "PLACE_PINS_ARGS": "-annealing",
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

# Placement density per block where the default spreads it too thin.
# MemBlock is ~37 % utilised with every pin on one edge: at 0.6 the
# dcache's port-less flop arrays drift to the empty far side and its worst
# path crosses the die twice; at 0.8 its period is 1,696 ps against 1,815,
# at 0.9 2,217 (over-packed). Place stage, dirty lane.
XS_PLACE_DENSITY = {
    "MemBlock": "0.8",
}

# The annealer's channel between facing macros, per block where the default
# does not serve it. CoupledL2's four data SRAMs keep every pin on one edge,
# and the annealer faces those edges across the channel: at 4 um no buffer
# fits beside the pins, write data and control cross the 332 um macro row
# unbuffered, and the block's period is 1,982 ps; at 12 um it is 1,437 ps
# (place stage, dirty lane).
XS_ANNEAL_CHANNEL_UM = {
    "CoupledL2": "12.0",
}

# Outline knobs a planned flow replaces with DIE_AREA/CORE_AREA, and the
# legaliser window the parent no longer needs once the channels are planned.
# SKIP_REPORT_METRICS stays on: report_metrics on a 3.7 M-instance parent
# runs for an hour per stage; slack is read from the stage ODB with
# odb-debug in seconds instead.
_PLAN_DROPS = ["CORE_UTILIZATION", "CORE_ASPECT_RATIO", "CORE_MARGIN", "DETAIL_PLACEMENT_ARGS"]

def _regfile_macro(spec, made, tags, outlines = {}, variant = None, pins = {}):
    """A generated register file as a macro of its own: its RTL module as
    a flow's top, generate_ram's netlist inlined there, implemented through
    global route like the blocks, its abstract for the parent (docs: a
    register file kept as a macro is a flow of its own, #1257). Each made
    once; returns the abstract's label.

    outlines maps a module to the plan's outline for it, {w_um, h_um}: a
    register file the plan places in the parent is built to the outline
    the plan left for it, as a block is, or it lands on its neighbours
    (MPL-0041). Without one, its size follows from its utilization.

    variant names a variant of every flow; pins maps a module to a pin
    plan's IO_CONSTRAINTS for it (//tools/pin_plan), its pins on the sides
    that face their logic in the parent."""
    module = spec.split(":")[-1].removesuffix(".regfile")
    if module not in made:
        made[module] = True
        size = {"CORE_UTILIZATION": "40"}
        if module in outlines:
            w, h = outlines[module]["w_um"], outlines[module]["h_um"]
            size = {
                "CORE_AREA": "%s %s %s %s" % (_REGFILE_MARGIN_UM, _REGFILE_MARGIN_UM, w - _REGFILE_MARGIN_UM, h - _REGFILE_MARGIN_UM),
                "DIE_AREA": "0 0 %s %s" % (w, h),
            }
        orfs_flow(
            name = module,
            abstract_stage = "grt",
            arguments = size | {
                "ASAP7_USE_VT": XS_VT,
                "AUTO_MEMORIES": "1",
                "GLOBAL_ROUTE_ARGS": "-congestion_iterations 0 -allow_congestion -verbose",
                "PLACE_DENSITY": "0.6",
                "SYNTH_HDL_FRONTEND": "slang",
            },
            pdk = "//flow:asap7",
            sources = {
                "AUTO_MEMORIES_REGFILES": [spec],
                # a block's grid, so its parent's macro grid connects to it
                "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
                "SDC_FILE": ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"],
            } | ({"IO_CONSTRAINTS": [pins[module]]} if module in pins else {}),
            # a variant changes nothing synthesis reads; shared only by a
            # flow without macros: a later stage takes its macros from its
            # src, synthesis, so a block or the parent sharing it would
            # place the base flow's
            previous_stage = {"floorplan": ":%s_synth" % module} if variant else {},
            stage_arguments = {"grt": {"HOLD_SLACK_MARGIN": "-1000"}},
            tags = tags,
            variant = variant,
            verilog_files = XS_VERILOG,
        )
    return _abstract(module, variant)

def _abstract(flow, variant):
    """A flow's abstract, of its variant."""
    if variant:
        return ":%s_%s_generate_abstract" % (flow, variant)
    return ":%s_generate_abstract" % flow

# The plans a pin plan variant reads: <part>_pin_plan from the part's
# global route, <part>_pin_plan_place from its placement. Whether the
# placement already says what the route says is what the second answers:
# if it does, a first pass need only reach place.
_PIN_PLAN_STAGES = {
    "pinplan": ("pin_plan", "grt"),
    "pinplan_place": ("pin_plan_place", "place"),
    "pinplan2": ("pin_plan2", "grt"),
}

# A second round: the pinplan variant's flows are planned again from
# their own global route, and the pinplan2 variant reads that plan. A
# plan moves logic as well as pins; whether a second round converges is
# what it answers.
_PIN_PLAN_NEXT = {"pinplan": "pinplan2"}

_STAGE_ODB = {"place": "3_place", "cts": "4_cts", "grt": "5_1_grt"}

def _pin_plan(name, stage, modules, tags, outdir = "pin_plan", variant = None):
    """<name>_<outdir>: //tools/pin_plan on a flow's stage (of a variant),
    its macros' pins (modules) planned from where their logic sits, the
    macros' places, and a report of the pins facing away from their logic:
    a pin plan variant's input, built forward from this pass, never
    checked in."""
    outs = ["%s/%s/%s_pins.tcl" % (outdir, name, m) for m in modules] + [
        "%s/%s/%s_macros.tcl" % (outdir, name, name),
        "%s/%s/%s_pins_report.txt" % (outdir, name, name),
    ]
    orfs_run(
        name = "%s_%s" % (name, outdir),
        src = ":%s_%s_%s" % (name, variant, stage) if variant else ":%s_%s" % (name, stage),
        outs = outs,
        script = "//tools/pin_plan:pin_plan.tcl",
        tags = tags,
        user_arguments = {
            "PINS_OUT": " ".join(["%s $(location %s/%s/%s_pins.tcl) 0 0" % (m, outdir, name, m) for m in modules]),
            "PIN_PLAN_PLACEMENT": "$(location %s/%s/%s_macros.tcl)" % (outdir, name, name),
            "PIN_PLAN_REPORT": "$(location %s/%s/%s_pins_report.txt)" % (outdir, name, name),
            "PIN_PLAN_STAGE": _STAGE_ODB[stage],
        },
    )

def _pin_plans(name, modules, tags):
    """A part's pin plans, from its placement and from its global route,
    and <name>_pin_plan_diff, the two side by side (pin_plan_diff.py)."""
    for variant in ["pinplan", "pinplan_place"]:
        outdir, stage = _PIN_PLAN_STAGES[variant]
        _pin_plan(name, stage, modules, tags, outdir)
    a, b = "pin_plan_place", "pin_plan"
    files = ["%s/%s/%s_pins_report.txt", "%s/%s/%s_macros.tcl"]
    srcs = []
    for f in files:
        srcs += [":" + f % (a, name, name), ":" + f % (b, name, name)]
    for m in modules:
        srcs += [":%s/%s/%s_pins.tcl" % (a, name, m), ":%s/%s/%s_pins.tcl" % (b, name, m)]
    native.genrule(
        name = "%s_pin_plan_diff" % name,
        srcs = srcs,
        outs = ["pin_plan_diff/%s.txt" % name],
        cmd = "$(execpath //tools/pin_plan:pin_plan_diff) $@ place grt " + " ".join(["$(location %s)" % s for s in srcs]),
        tags = tags,
        tools = ["//tools/pin_plan:pin_plan_diff"],
    )

def _pins_after(name, variant, tags):
    """<name>_<variant>_pins_after: the variant's macro pins at its global
    route, the same table as the plan's report, nothing planned."""
    out = "%s_pins_after/%s_pins_report.txt" % (variant, name)
    orfs_run(
        name = "%s_%s_pins_after" % (name, variant),
        src = ":%s_%s_grt" % (name, variant),
        outs = [out],
        script = "//tools/pin_plan:pin_plan.tcl",
        tags = tags,
        user_arguments = {
            "PINS_OUT": "",
            "PIN_PLAN_REPORT": "$(location %s)" % out,
            "PIN_PLAN_STAGE": _STAGE_ODB["grt"],
        },
    )

# a planned register file's core inside its outline: no ring on a
# macro's BLOCK grid, so only the row and pin clearance
_REGFILE_MARGIN_UM = 2.0

def _regfiles(own_sources, keep, blocks):
    """The generated register files a planned flow hardens: its own, plus
    those of every block of the old table whose module it now keeps (the
    Ftq queues inside Frontend, the int register file and the ROB's files
    in the parent), each once."""
    out = list(own_sources.get("AUTO_MEMORIES_REGFILES", []))
    for k in [k for k in keep.split(" ") if k]:
        for m in blocks.get(k, {}).get("sources", {}).get("AUTO_MEMORIES_REGFILES", []):
            if m not in out:
                out.append(m)
    return out

# Every flow maps and repairs with all three of asap7's threshold voltages,
# RVT first as the primary. A .odb fixes its cell masters at floorplan, so
# this is a synthesis-onward setting: set on a later stage alone it reads the
# extra liberty and adds no masters (.claude/skills/byo-openroad).
XS_VT = "RVT LVT SLVT"

def _planned_block(cfg, entry, plan_dir, block, blocks):
    """A block flow's arguments and sources under the plan: planned outline,
    every pin on the planned side, the parent's target period."""
    arguments = {k: v for k, v in cfg["arguments"].items() if k not in _PLAN_DROPS}
    arguments["DIE_AREA"] = entry["DIE_AREA"]
    arguments["CORE_AREA"] = entry["CORE_AREA"]

    # The block is implemented through global route and abstracted there,
    # as a macro is: its clock tree built and its timing repaired with the
    # route's parasitics, which is what the parent's paths through the
    # block are timed against. Route-0 with congestion allowed, as the
    # parent routes: the repair and the parasitics move the period, and a
    # block's maze iterations take hours.
    arguments["GLOBAL_ROUTE_ARGS"] = "-congestion_iterations 0 -allow_congestion -verbose"

    # Pin access stops on one generated SRAM pin in MemBlock (DRT-0073,
    # array_32x148's RW0_clk), as it does on the parent's block pins.
    # Skipped as the parent skips it; carried ORFS patch 0085 retires
    # with the bug.
    arguments["SKIP_PIN_ACCESS"] = "1"

    # Synthesis keeps exactly the plan's modules and flattens the rest,
    # stated rather than left to SYNTH_HIERARCHICAL=1's rule, and OpenROAD
    # keeps that hierarchy.
    if "SYNTH_KEEP_MODULES" not in entry:
        fail("planned block %s states no SYNTH_KEEP_MODULES; a block keeps the modules its plan names, and only those" % block)
    arguments["SYNTH_KEEP_MODULES"] = entry["SYNTH_KEEP_MODULES"]
    arguments["SYNTH_HIERARCHICAL"] = "0"
    if block in XS_PLACE_DENSITY:
        arguments["PLACE_DENSITY"] = XS_PLACE_DENSITY[block]
    arguments["OPENROAD_HIERARCHICAL"] = "1"
    arguments["ASAP7_USE_VT"] = XS_VT
    sources = dict(cfg["sources"])

    # the block's register files are macros of their own (_regfile_macro)
    sources.pop("AUTO_MEMORIES_REGFILES", None)
    sources["IO_CONSTRAINTS"] = [":%s/%s_pins.tcl" % (plan_dir, block)]
    sources["SDC_FILE"] = ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"]
    return arguments, sources

def _kpi(part, stage, arguments, sources, tags, variant = None):
    """<part>_kpi: the part's reg2reg period and each group's worst path, read
    in the build from its own stage (kpi_run.tcl), so the number is the
    build's and needs no session. Of a variant, <part>_<variant>_kpi."""
    flow = "%s_%s" % (part, variant) if variant else part
    orfs_run(
        name = "%s_kpi" % flow,
        src = ":%s_%s" % (flow, stage),
        outs = ["%s_kpi.txt" % flow],
        arguments = arguments,
        script = "//test/coremark_joule/designs/asap7/xiangshan:kpi_run.tcl",
        sources = sources,
        tags = tags,
        user_arguments = {
            "KPI_OUT": "$(location %s_kpi.txt)" % flow,
            "KPI_STAGE": stage,
        },
        variant = variant,
    )

def _sta_part(part, arguments, sources, tags, ilm = False):
    """<part>_sta_part: the part at global route as sta_flat.tcl reads it: its
    netlist read flat, the route's parasitics, its SDC and its liberty files."""
    outs = ["%s.v" % part, "%s.spef" % part, "%s.sdc" % part, "%s_libs.tar" % part]
    orfs_run(
        name = "%s_sta_part" % part,
        src = ":%s_grt" % part,
        outs = ["sta/%s" % o for o in outs],
        arguments = arguments,
        script = "//test/coremark_joule/designs/asap7/xiangshan:sta_part.tcl",
        sources = sources,
        tags = tags,
        user_arguments = {
            "PART_LIBS": "$(location sta/%s_libs.tar)" % part,
            "PART_SDC": "$(location sta/%s.sdc)" % part,
            "PART_SPEF": "$(location sta/%s.spef)" % part,
            "PART_V": "$(location sta/%s.v)" % part,
            "STA_ILM": "1" if ilm else "0",
        },
    )

def xiangshan_flow(name, plan, blocks = XS_BLOCKS, parent = XS_PARENT, tags = ["manual"], plan_dir = "plan", variant = None):
    """The plan's blocks, each implemented through global route, then the parent.

    `plan` is the PLAN dict plan_floorplan.py --emit wrote to
    plan_dir/plan.bzl: each block a real flow at the planned outline with
    its pins on the planned side, the parent at the planned die with
    plan_dir/place_macros.tcl placing the blocks R0 where the plan put
    them. The blocks are abstracted at grt, so the parent's CTS and
    timing see each block's clock pin as its tree's root buffer and its
    insertion delay, not the whole unbuffered clock net (entry 17 of
    ideas/xiangshan-timing.md), and its timing as repaired with the
    route's parasitics; the parent's synthesis, floorplan and place read
    the place-stage abstract the flow emits beside it. Every part's KPI is
    read at grt.

    Without a variant, <part>_pin_plan plans each part's register-file
    pins and macro places from its grt (//tools/pin_plan),
    <part>_pin_plan_place from its place, and <part>_pin_plan_diff sets
    the two side by side. With a variant (_PIN_PLAN_STAGES), every flow is
    that variant of itself and reads one of those plans, forward from the
    base flow in one graph: the register files' pins on the sides facing
    their logic, each block's macros where the plan was made, the register
    files' synthesis shared with the base flow, and
    <part>_<variant>_pins_after the pins facing away at its grt. The KPI
    and the stitched views stay the base flow's.
    """
    macros = sorted(plan["macros"].keys())
    made = {}

    # each register file's pins from the plan of the part it is a macro of
    pins = {}
    places = {}
    planned = []
    if variant:
        outdir = _PIN_PLAN_STAGES[variant][0]
        for block in macros:
            entry = plan["macros"][block]
            cfg = blocks.get(block, XS_BLOCK_DEFAULT)
            places[block] = ":%s/%s/%s_macros.tcl" % (outdir, block, block)
            for m in _regfiles(cfg["sources"], entry.get("SYNTH_KEEP_MODULES", ""), blocks):
                module = m.split(":")[-1].removesuffix(".regfile")
                pins[module] = ":%s/%s/%s_pins.tcl" % (outdir, block, module)
    for block in macros:
        cfg = blocks.get(block, XS_BLOCK_DEFAULT)
        if block in XS_ANNEAL_CHANNEL_UM:
            cfg = dict(cfg, user_arguments = cfg["user_arguments"] | {"ANNEAL_CHANNEL_UM": XS_ANNEAL_CHANNEL_UM[block]})
        entry = plan["macros"][block]
        arguments, sources = _planned_block(cfg, entry, plan_dir, block, blocks)
        modules = _regfiles(cfg["sources"], entry.get("SYNTH_KEEP_MODULES", ""), blocks)
        if variant and not modules:
            # nothing planned: its macros would be fixed where the base
            # flow put them, so the variant's parent reads the base flow's
            continue
        planned.append(block)
        regfiles = [_regfile_macro(m, made, tags, variant = variant, pins = pins) for m in modules]
        if block in places:
            # the macros where the pin plan's placement put them, so the
            # planned pins face their logic
            sources = dict(sources, MACRO_PLACEMENT_TCL = [places[block]])

        # The parent places the block's footprint, its outline scaled so its
        # core holds the block's content at the plan's block_density; the
        # mocked abstract carries that outline and its pins, the block's own
        # flow its timing. The block's own density is its own concern.
        mock = {}
        if "MOCK_AREA" in entry:
            mock = {
                "mock_area": float(entry["MOCK_AREA"]),
                "mock_sources": {"IO_CONSTRAINTS": [":%s/%s_mock_pins.tcl" % (plan_dir, block)]},
            }
        verilog, arguments, sources, user_arguments = _extracted(block, arguments, sources, cfg["user_arguments"] | XS_ICG_USER_ARGUMENTS)
        user_sources = cfg["user_sources"] | XS_ICG_USER_SOURCES
        orfs_flow(
            name = block,
            abstract_stage = "grt",
            arguments = arguments,
            macros = regfiles,
            # hold stays with CTS's repair, as the parent's
            stage_arguments = {"grt": {"HOLD_SLACK_MARGIN": "-1000"}},
            pdk = "//flow:asap7",
            sources = sources,
            tags = tags,
            user_arguments = user_arguments,
            user_sources = user_sources,
            user_stages = _user_stages(user_arguments, user_sources),
            variant = variant,
            verilog_files = verilog,
            **mock
        )
        if variant:
            _kpi(block, "grt", arguments, sources, tags, variant)
            _pins_after(block, variant, tags)
            if variant in _PIN_PLAN_NEXT:
                _pin_plan(block, "grt", [m.split(":")[-1].removesuffix(".regfile") for m in modules], tags, _PIN_PLAN_STAGES[_PIN_PLAN_NEXT[variant]][0], variant)
            continue
        _kpi(block, "grt", arguments, sources, tags)
        _sta_part(block, arguments, sources, tags, ilm = True)
        _pin_plans(block, [m.split(":")[-1].removesuffix(".regfile") for m in modules], tags)
    arguments = {k: v for k, v in parent["arguments"].items() if k not in _PLAN_DROPS}
    arguments["DIE_AREA"] = plan["parent"]["DIE_AREA"]
    arguments["CORE_AREA"] = plan["parent"]["CORE_AREA"]
    arguments["ASAP7_USE_VT"] = XS_VT

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
    #
    # 0.3, not 0.2: the parent's utilization is 0.18, and at 0.2 global
    # placement cannot bring overflow under its target. It runs to about
    # 0.19 and diverges (GPL-0307) on the OpenROAD this module bumps to;
    # older ones reverted to that snapshot and carried on. At 0.3 it
    # converges cleanly, overflow under 0.1 by iteration 550, still far
    # from take 23's 60 percent.
    arguments["PLACE_DENSITY"] = "0.3"
    arguments["ROUTING_LAYER_ADJUSTMENT"] = "0.1"

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

    # the parent's register files are macros of their own (_regfile_macro)
    outlines = {n["module"]: n for n in plan["parent"].get("netlists", [])}
    parent_modules = _regfiles(parent["sources"], parent_keep, blocks)
    if variant:
        for m in parent_modules:
            module = m.split(":")[-1].removesuffix(".regfile")
            pins[module] = ":%s/%s/%s_pins.tcl" % (_PIN_PLAN_STAGES[variant][0], name, module)
    parent_regfiles = [_regfile_macro(m, made, tags, outlines, variant = variant, pins = pins) for m in parent_modules]
    sources.pop("AUTO_MEMORIES_REGFILES", None)

    # the plan's blocks and register files, placed by the plan
    sources["MACRO_PLACEMENT_TCL"] = [":%s/place_macros.tcl" % plan_dir]
    if plan["parent"].get("pins"):
        # every port on the plan's port side, the edge facing the NoC
        sources["IO_CONSTRAINTS"] = [":%s/%s" % (plan_dir, plan["parent"]["pins"])]

    # Every legalization of the parent -- placement's, CTS's two, global
    # route's -- first moves each movable cell the resizer or CTS left
    # inside a hard block to just outside the block's nearest edge: there
    # is no row under it, and the legaliser can only find it a site within
    # its window. Without it detailed placement fails on a few of the
    # thousands of buffers left there (DPL-0036).
    for hook in ["PRE_DETAIL_PLACE_TCL", "PRE_CTS_TCL", "PRE_GLOBAL_ROUTE_TCL"]:
        sources[hook] = ["//test/coremark_joule/designs/asap7/xiangshan:legalize_out_of_blocks.tcl"]
    sources["SDC_FILE"] = ["//test/coremark_joule/designs/asap7/xiangshan:constraints.sdc"]
    verilog, arguments, sources, user_arguments = _extracted("parent", arguments, sources, XS_ICG_USER_ARGUMENTS)
    user_sources = XS_ICG_USER_SOURCES
    orfs_flow(
        name = name,
        arguments = arguments,
        macros = [_abstract(b, variant if b in planned else None) for b in macros] + parent_regfiles,
        # The parent repairs setup at global route, with the route's
        # parasitics: 3,276 to 2,406 ps on #1187's tip (KPI row 15), its
        # worst paths a mass of CtrlBlock control that the repairs before
        # the route time with estimated wires. Hold stays with CTS's
        # repair: this stage's hold repair took an earlier run of it to
        # 120 GB, and -1000 ps turns it off here. The stage costs 84 min
        # against 19 and peaks at 102 GB against 83.
        stage_arguments = {"grt": {"HOLD_SLACK_MARGIN": "-1000"}},
        pdk = "//flow:asap7",
        sources = sources,
        tags = tags,
        user_arguments = user_arguments,
        user_sources = user_sources,
        user_stages = _user_stages(user_arguments, user_sources),
        variant = variant,
        verilog_files = verilog,
        visibility = ["//visibility:public"],
    )
    if variant:
        _kpi(name, "grt", arguments, sources, tags, variant)
        _pins_after(name, variant, tags)
        if variant in _PIN_PLAN_NEXT:
            _pin_plan(name, "grt", [m.split(":")[-1].removesuffix(".regfile") for m in parent_modules], tags, _PIN_PLAN_STAGES[_PIN_PLAN_NEXT[variant]][0], variant)
        return
    _pin_plans(name, [m.split(":")[-1].removesuffix(".regfile") for m in parent_modules], tags)
    _kpi(name, "grt", arguments, sources, tags)
    _sta_part(name, arguments, sources, tags)
    parts = [name] + list(macros)

    # with wires (the KPI) and without (each path's logic alone)
    for suffix, wires in [("", "1"), ("_nowire", "0")]:
        native.genrule(
            name = "%s_kpi_flat%s" % (name, suffix),
            srcs = [":%s_sta_part" % p for p in parts] + [":sta_flat.tcl", "//tools/headroom:classify.tcl"] +
                   [":sta/%s.%s" % (p, ext) for p in parts for ext in ["v", "spef", "sdc"]] +
                   [":sta/%s_libs.tar" % p for p in parts],
            outs = ["%s_kpi_flat%s.txt" % (name, suffix), "%s_kpi_flat%s_paths.txt" % (name, suffix)],
            # each block's modules renamed <block>__<module> (sta_prefix.py), the
            # rest beside them in one directory sta_flat.tcl reads
            cmd = " && ".join([
                "w=$$(mktemp -d)",
                "for f in $(execpath :sta/%s.v) %s; do ln -s $$PWD/$$f $$w/; done" % (
                    name,
                    " ".join(["$(execpath :sta/%s.%s)" % (p, ext) for p in parts for ext in ["spef", "sdc"]] +
                             ["$(execpath :sta/%s_libs.tar)" % p for p in parts]),
                ),
            ] + [
                "$(execpath :sta_prefix) %s $(execpath :sta/%s.v) $$w/%s.v" % (b, b, b)
                for b in macros
            ] + [
                "ulimit -s unlimited",
                "STA_CLASSIFY=$(execpath //tools/headroom:classify.tcl) STA_DIR=$$w STA_PARENT=%s STA_PARTS='%s' STA_WIRES=%s STA_OUT=$(location %s_kpi_flat%s.txt) STA_PATHS=$(location %s_kpi_flat%s_paths.txt) $(execpath @openroad//src/sta:opensta) -no_splash -threads max -exit $(execpath :sta_flat.tcl)" % (name, " ".join(parts), wires, name, suffix, name, suffix),
            ]),
            tools = [":sta_prefix", "@openroad//src/sta:opensta"],
            tags = tags,
        )

    # how much of the period repair left, and in which move: wire, VT,
    # skew, retiming; the floors no repair beats (repair-headroom skill)
    orfs_headroom(
        name = "%s_headroom" % name,
        parent = name,
        parent_stage = ":%s_grt" % name,
        blocks = {b: ":%s_grt" % b for b in macros},
        # the goal; the SDC's 473 ps makes nearly every endpoint violate
        target = 2000,
        tags = tags,
    )

def xiangshan_flat_flow(name, variant, parent = XS_PARENT, blocks = XS_BLOCKS, tags = ["manual"]):
    """The whole tile as one flow, <name>_<variant>_<stage>: no hardened blocks.

    ORFS's own hierarchical synthesis (SYNTH_HIERARCHICAL with its keep
    rule, not a plan's SYNTH_KEEP_MODULES), then floorplan to global route
    on the one netlist, so macro placement and global placement see every
    cell and every macro of the tile at once. OPENROAD_HIERARCHICAL keeps
    the kept modules in the ODB, so the hierarchy is there to look at.

    The register files are the macros xiangshan_flow makes, the same
    targets, so a build of either reuses the other's; declare this after
    it. The memories are AUTO_MEMORIES', as in every flow. The rest is
    the planned parent's global route settings.
    """
    arguments = {k: v for k, v in parent["arguments"].items() if k != "SYNTH_KEEP_MODULES"}
    arguments["ASAP7_USE_VT"] = XS_VT

    # the planned parent's route, which is what this one is compared with:
    # zero iterations with congestion allowed, the congestion map and
    # stop; pin access skipped on the generated macros' pins (DRT-0073,
    # carried ORFS patch 0085)
    arguments["GLOBAL_ROUTE_ARGS"] = "-congestion_iterations 0 -allow_congestion -verbose"
    arguments["SKIP_PIN_ACCESS"] = "1"
    arguments["ROUTING_LAYER_ADJUSTMENT"] = "0.1"
    arguments["MAX_ROUTING_LAYER"] = "M9"
    arguments["MIN_ROUTING_LAYER"] = "M2"
    sources = dict(parent["sources"])
    sources.pop("AUTO_MEMORIES_REGFILES", None)

    # cells the resizer or CTS leave inside a register file's footprint,
    # out before each legalization (DPL-0036), as in the planned parent
    for hook in ["PRE_DETAIL_PLACE_TCL", "PRE_CTS_TCL", "PRE_GLOBAL_ROUTE_TCL"]:
        sources[hook] = ["//test/coremark_joule/designs/asap7/xiangshan:legalize_out_of_blocks.tcl"]

    # every register file of the tile, each the macro xiangshan_flow made
    specs = list(parent["sources"].get("AUTO_MEMORIES_REGFILES", []))
    for cfg in blocks.values():
        for m in cfg.get("sources", {}).get("AUTO_MEMORIES_REGFILES", []):
            if m not in specs:
                specs.append(m)
    regfiles = [":%s_generate_abstract" % m.split(":")[-1].removesuffix(".regfile") for m in sorted(specs)]
    user_arguments = parent["user_arguments"] | XS_ICG_USER_ARGUMENTS
    user_sources = parent["user_sources"] | XS_ICG_USER_SOURCES
    orfs_flow(
        name = name,
        arguments = arguments,
        macros = regfiles,
        # hold stays with CTS's repair, as the planned parent's
        stage_arguments = {"grt": {"HOLD_SLACK_MARGIN": "-1000"}},
        pdk = "//flow:asap7",
        sources = sources,
        tags = tags,
        user_arguments = user_arguments,
        user_sources = user_sources,
        user_stages = _user_stages(user_arguments, user_sources),
        variant = variant,
        verilog_files = XS_VERILOG,
    )
    _kpi(name, "grt", arguments, sources, tags, variant = variant)
