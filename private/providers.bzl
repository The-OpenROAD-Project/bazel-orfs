"""Provider declarations for OpenROAD-flow-scripts Bazel rules."""

OrfsInfo = provider(
    "The outputs of a OpenROAD-flow-scripts stage.",
    fields = [
        "stage",
        "config",
        "variant",
        "odb",
        "sdc",
        "gds",
        "lef",
        "lib",
        "lib_pre_layout",
        "additional_gds",
        "additional_lefs",
        "additional_libs",
        "additional_libs_pre_layout",
        "arguments",
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
        "files",
        "runfiles",
    ],
)

LoggingInfo = provider(
    "Logs and reports for current and previous stages",
    fields = [
        # The directory the flow's logs accumulate in, exec-root relative.
        # A consuming orfs_run cannot derive it: it depends on the package
        # and variant of the flow, not of the consumer.
        "log_dir",
        "logs",
        "reports",
        "drcs",
        "jsons",
    ],
)
