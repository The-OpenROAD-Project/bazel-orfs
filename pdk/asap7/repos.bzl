"""Repository rule fetching the cell views added in asap7sc7p5t_28 PR #13.

The full asap7sc7p5t_28 GitHub archive is over 3 GB (36 CCS/CCSA/CCSN
libraries per cell family plus HTML datasheets and extracted SPICE).
Fetching only the files ORFS's asap7 platform consumes keeps the download
to ~26 MB and verifies each file individually by sha256.
"""

ASAP7SC7P5T_28_COMMIT = "8ddba91f4d05f8696f020f512d7ac60f4d37e797"

ASAP7SC7P5T_28_URL_PREFIX = (
    "https://raw.githubusercontent.com/The-OpenROAD-Project/asap7sc7p5t_28/" +
    ASAP7SC7P5T_28_COMMIT + "/"
)

# Relative path in asap7sc7p5t_28 -> sha256.
ASAP7SC7P5T_28_FILES = {
    "GDS/asap7sc7p5t_28_L_220121a.gds": "f8c315a2e96ebd3c7d1bc5710d66bc8296b740b650c6425b87a56e10922c43ae",
    "GDS/asap7sc7p5t_28_R_220121a.gds": "8a2fbbdd7b0120e6fc8e047162b60896f632b0215a016e9e3c37dd70348daba4",
    "GDS/asap7sc7p5t_28_SL_220121a.gds": "b55c3bd8e18ef3911fdfd942ad8ed999e2ebd4b61b833313781985234d12f4c3",
    "GDS/asap7sc7p5t_28_SRAM_220121a.gds": "1b6b7767b2ed46a3c204c2c6b4fdae97bbfdfcaab14f2282f701dab55e091a5a",
    "LEF/asap7sc7p5t_28_L_1x_220121a.lef": "180aaf18c29138649c6b48e99f2086223ac7be399521fec722763540dc9a2f03",
    "LEF/asap7sc7p5t_28_R_1x_220121a.lef": "a4a41688f164b2d3230d08d3022f6c299f1bee833936a92da9f1e70c0ae1beb3",
    "LEF/asap7sc7p5t_28_SL_1x_220121a.lef": "fdba3dcb9c62919f14d65adba88be9bcaac3bcf6a4dadc6c38a05d76f5db7e51",
    "LEF/asap7sc7p5t_28_SRAM_1x_220121a.lef": "db914b30f0a7f25bf13a7c5df9380be39482c72c329ccdc75f16ec01e80b5ff9",
    "LIB/CCS/asap7sc7p5t_ADDED_RVT_FF_ccs_261116.lib.7z": "ba60830a59ec7c51563bc2046d3e349b2a82cc81b66426ea18fe0eb591cecc57",
    "LIB/NLDM/asap7sc7p5t_ADDED_LVT_FF_nldm_261116.lib.7z": "0a9c71491c9373f82197242166d3b23045621f6cb8c366c0926f37db3b71d80c",
    "LIB/NLDM/asap7sc7p5t_ADDED_LVT_SS_nldm_261116.lib.7z": "ba491a2065243d8a0d91519f1572664df7a42fc11f2d2f8e20926d965d822ff0",
    "LIB/NLDM/asap7sc7p5t_ADDED_LVT_TT_nldm_261116.lib.7z": "814512063109912a7466f4c038849b7922b0de7d5965bbfd4acbd1a5fd11172c",
    "LIB/NLDM/asap7sc7p5t_ADDED_RVT_FF_nldm_261116.lib.7z": "83583863755ab641c19afde9ad4b3543742e7a1ba253a172ddaf17ed835d6ce3",
    "LIB/NLDM/asap7sc7p5t_ADDED_RVT_SS_nldm_261116.lib.7z": "59ffcf2d1896bebf43dc4669e6ace9ac3f8611fe549a0727db19e4dbc48e1378",
    "LIB/NLDM/asap7sc7p5t_ADDED_RVT_TT_nldm_261116.lib.7z": "43d588c50e99869fe0418b3c3a456acd654e9c90fccea44f6789ca02c53b91a0",
    "LIB/NLDM/asap7sc7p5t_ADDED_SLVT_FF_nldm_261116.lib.7z": "ab4152366c537153b953cef1c3e3f1f5a7f34d1446939e769d48539c5bb5676f",
    "LIB/NLDM/asap7sc7p5t_ADDED_SLVT_SS_nldm_261116.lib.7z": "aea2b0e4991aa79b7b559b5d145822c8fa4c3b07d8212e060eab197de223d034",
    "LIB/NLDM/asap7sc7p5t_ADDED_SLVT_TT_nldm_261116.lib.7z": "6c7b8226b343f3feb16643fff462102446fb9ed7d7a7ac444f0108da13e2d6e5",
    "LIB/NLDM/asap7sc7p5t_ADDED_SRAM_FF_nldm_261116.lib.7z": "05d7ad3b70aeaebb1c0768bc481c925dcec5565e79ba33622e9b22810953f3d3",
    "LIB/NLDM/asap7sc7p5t_ADDED_SRAM_SS_nldm_261116.lib.7z": "06702af60d36a0ecdde079892aab8ad7a67d1d91417498ff8eca6846e67ee43c",
    "LIB/NLDM/asap7sc7p5t_ADDED_SRAM_TT_nldm_261116.lib.7z": "62420dd44df96cd1dceb44dc418ca95ad8ac483c1b39c27a07499f05b29ea3a8",
    "Verilog/asap7sc7p5t_ADDED_LVT_TT_261116.v": "d99e0b04d731141b70a8807b103687e0014059f31144cd5d17c053d079d3cad5",
    "Verilog/asap7sc7p5t_ADDED_RVT_TT_261116.v": "f2ea2021dda862e9d23b46a090820ae521d2f3cb78e5c6c70a08ed3db4950e3a",
    "Verilog/asap7sc7p5t_ADDED_SLVT_TT_261116.v": "5f74e6ade0b5f100189daf9808627ec0f3fa6102fbcd8ec7de2eb5d75b9bc8bc",
    "Verilog/asap7sc7p5t_ADDED_SRAM_TT_261116.v": "8fa87cd1eb2cf140a85bd2af4bba3a07cd5c564de9026fc2475651fb81ac22f8",
}

def _asap7sc7p5t_28_impl(repository_ctx):
    pending = [
        repository_ctx.download(
            url = ASAP7SC7P5T_28_URL_PREFIX + path,
            output = path,
            sha256 = sha256,
            block = False,
        )
        for path, sha256 in sorted(ASAP7SC7P5T_28_FILES.items())
    ]
    for token in pending:
        token.wait()

    exports = ",\n    ".join([
        '"{}"'.format(path)
        for path in sorted(ASAP7SC7P5T_28_FILES.keys())
    ])
    repository_ctx.file(
        "BUILD.bazel",
        'exports_files([\n    {},\n], visibility = ["//visibility:public"])\n'.format(exports),
    )

asap7sc7p5t_28 = repository_rule(
    implementation = _asap7sc7p5t_28_impl,
    doc = "Downloads the updated LEF/GDS and ADDED Liberty/Verilog files from asap7sc7p5t_28.",
)
