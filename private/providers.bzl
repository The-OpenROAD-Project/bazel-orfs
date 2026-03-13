"""Provider declarations for OpenROAD-flow-scripts Bazel rules."""

OrfsInfo = provider(
    "The outputs of a OpenROAD-flow-scripts stage.",
    fields = [
        "stage",
        "config",
        "variant",
        "odb",
        "gds",
        "lef",
        "lib",
        "additional_gds",
        "additional_lefs",
        "additional_libs",
    ],
)
PdkInfo = provider(
    "A process design kit.",
    fields = [
        "name",
        "files",
        "config",
        "libs",
    ],
)
TopInfo = provider(
    "The name of the netlist top module.",
    fields = ["module_top"],
)

OrfsDepInfo = provider(
    "The name of the netlist top module.",
    fields = [
        "make",
        "config",
        "renames",
        "files",
        "runfiles",
    ],
)

LoggingInfo = provider(
    "Logs and reports for current and previous stages",
    fields = [
        "logs",
        "reports",
        "drcs",
        "jsons",
    ],
)
