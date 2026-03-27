# Per-module netlist synthesis: modules with >1000 cells from survey.
# Each module is synthesized independently with all others blackboxed.
# Bazel runs these as parallel actions = parallel ABC.
KEPT_MODULES = [
    # >10K cells
    "PipelinedMultiplier",  # 17,686
    "BoomFrontend",  # 11,273
    # >5K cells
    "CSRFile",  #  8,944
    "ITLB",  #  7,898
    "BoomCore",  #  7,339
    "Arbiter9_BoomDCacheResp",  #  7,083
    "RenameFreeList_2",  #  5,950
    "FPExeUnit_1",  #  5,782
    "BoomRAS",  #  5,694
    "BasicDispatcher",  #  5,660
    "UniqueExeUnit",  #  5,582
    "ICache",  #  5,385
    "RenameBusyTable",  #  5,355
    "BTBBranchPredictorBank",  #  5,225
    "Arbiter8_BoomDCacheReqInternal",  # 5,159
    "Queue1_FetchBundle_1",  #  5,116
    # >3K cells
    "RenameBusyTable_1",  #  4,993
    "RocketALU",  #  4,979
    "LoopBranchPredictorColumn",  #  4,582
    "Queue1_FetchBundle",  #  4,575
    "MulAddRecFNToRaw_postMul_e11_s53",  # 4,457
    "MulDiv",  #  4,263
    "Queue1_BranchPredictionBundle",  # 4,105
    "BranchPredictor",  #  3,926
    "RenameStage_1",  #  3,904
    "FPExeUnit",  #  3,758
    "BranchKillablePipeline_2",  #  3,751
    "MulAddRecFNPipe_l2_e8_s24",  #  3,016
    "FpPipeline",  #  3,003
    # >2K cells
    "ALUExeUnit_1",  #  2,748
    "PartiallyPortedRF_1",  #  2,727
    "ALUExeUnit",  #  2,722
    "ALUExeUnit_2",  #  2,722
    "ALUExeUnit_3",  #  2,722
    "IssueSlot_64",  #  2,614
    "IssueSlot",  #  2,478
    "BoomWritebackUnit",  #  2,476
    "TageBranchPredictorBank",  #  2,460
    "BranchKillableQueue_1",  #  2,444
    "BranchKillableQueue_18",  #  2,366
    "BankedRF_1",  #  2,330
    "ALUUnit",  #  2,213
    "IntToFP",  #  2,190
    "DivSqrtRawFN_small_e11_s53",  # 2,186
    "BoomMSHR",  #  2,145
    "MemExeUnit_1",  #  2,072
    # >1K cells
    "FPToInt",  #  1,891
    "BranchKillablePipeline_1",  #  1,887
    "MulAddRecFNToRaw_preMul_e11_s53",  # 1,880
    "MulAddRecFNToRaw_postMul_e8_s24",  # 1,872
    "BranchKillableQueue_17",  #  1,823
    "RecFNToIN_e11_s53_i64",  #  1,791
    "FPToFP",  #  1,691
    "FPU",  #  1,652
    "PredRenameStage",  #  1,572
    "Arbiter8_L1DataWriteReq",  #  1,552
    "PartiallyPortedRF",  #  1,452
    "AMOALU",  #  1,433
    "BIMBranchPredictorBank",  #  1,380
    "INToRecFN_i64_e11_s53",  #  1,365
    "INToRecFN_i64_e8_s24",  #  1,365
    "PMPChecker_s3",  #  1,353
    "PMPChecker_s4",  #  1,329
    "MemExeUnit",  #  1,273
    "RoundAnyRawFNToRecFN_ie11_is55_oe11_os53",  # 1,244
    "FPUFMAPipe_l4_f64",  #  1,172
    "TageTable_5",  #  1,150
    "DivSqrtRawFN_small_e8_s24",  #  1,106
    "DecodeUnit",  #  1,050
    "TageTable_4",  #  1,037
    # Hierarchy-only modules (0 own cells, large sub-hierarchy area)
    "LSU",  # 52,809 μm²
    "IssueUnitCollapsing_3",  # 12,764 μm²
    "IssueUnitCollapsing",  # 12,165 μm²
    "IssueUnitCollapsing_2",  #  6,339 μm²
    "RenameMapTable",  #  6,261 μm²
    "FetchBuffer",  #  5,794 μm²
    "RenameMapTable_1",  #  5,486 μm²
    "FetchTargetQueue",  #  4,407 μm²
    "BranchKillableQueue",  #  4,134 μm²
    "RenameFreeList",  #  3,466 μm²
    "Rob",  #  3,324 μm²
    "RenameFreeList_1",  #  3,069 μm²
    "BoomMSHRFile",  #  2,999 μm²
    "IssueUnitCollapsing_1",  #  2,762 μm²
    "BoomBankedDataArray",  #  2,373 μm²
    "BranchKillableQueue_19",  #  2,266 μm²
    "FA2MicroBTBBranchPredictorBank",  # 1,903 μm²
    "BoomNonBlockingDCache",  #  1,742 μm²
    "PTW",  #  1,305 μm²
    "NBDTLB",  #  1,296 μm²
    "MulAddRecFNPipe_l2_e11_s53",  # 1,286 μm²
    "RenameStage",  #  1,061 μm²
    # Top-level
    "BoomTile",
]
