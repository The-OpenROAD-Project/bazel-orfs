"""Macro to create orfs_flow() targets from parsed config.mk data.

Call orfs_design() from a design's BUILD.bazel to auto-generate
orfs_flow() targets based on the design's config.mk.

The orfs_designs repository rule (designs.bzl) must be instantiated
first to parse all config.mk files and generate the DESIGNS dict.
"""

load(
    "//private:flow.bzl",
    "orfs_flow",
)
load(
    "//private:utils.bzl",
    "NUM_CPUS",
)

def _convert_sources(sources, pkg):
    """Convert absolute source labels to relative when in the current package.

    Filters out unresolvable labels (unresolved Make variables, invalid paths).
    """
    result = {}
    for var, labels in sources.items():
        converted = []
        for label in labels:
            # Skip unresolved Make variables
            if "$(" in label or "${" in label:
                continue

            # Skip invalid paths like //./
            if "//." in label:
                continue

            # Platform paths (fakeram lef/lib) are needed by the flow
            # Skip partial patterns and directory refs
            if "*" in label or "))" in label:
                continue

            # Skip empty targets (trailing colon with no name)
            if label.endswith(":"):
                continue
            if label.startswith("//" + pkg + ":"):
                label = ":" + label.split(":")[1]
            converted.append(label)
        if converted:
            result[var] = converted
    return result

def orfs_design(name = None, platform = None, design = None, designs = None, mock_openroad = None):  # buildifier: disable=unused-variable
    """Create orfs_flow() targets for a design based on its parsed config.mk.

    Call this from a design's BUILD.bazel:
        load("@bazel-orfs//:openroad.bzl", "orfs_design")
        load("@orfs_designs//:designs.bzl", "DESIGNS")
        orfs_design(designs = DESIGNS)

    The platform and design are auto-detected from the package path
    (flow/designs/<platform>/<design>/).

    Args:
        name: Unused, required by Bazel macro convention.
        platform: Override platform (default: from package path).
        design: Override design nickname (default: from package path).
        designs: The DESIGNS dict from the orfs_designs repository rule.
        mock_openroad: Label for mock-openroad binary. When set, generates
            lint flow targets (variant="lint") alongside real flow targets.
            Example: "@mock-openroad//src/bin:openroad".
    """
    if designs == None:
        fail("orfs_design() requires designs argument: pass DESIGNS from @orfs_designs//:designs.bzl")

    native.exports_files(
        native.glob(["*"]),
        visibility = ["//visibility:public"],
    )

    # Create filegroups for wildcard source patterns (e.g. ADDITIONAL_LEFS)
    existing_rules = native.existing_rules()
    for fg_name, fg_glob in [
        ("lef", ["*.lef"]),
        ("lib", ["*.lib"]),
        ("gds", ["*.gds.gz"]),
        ("verilog", ["*.v", "*.sv"]),
    ]:
        if fg_name not in existing_rules:
            srcs = native.glob(fg_glob, allow_empty = True)
            if srcs:
                native.filegroup(
                    name = fg_name,
                    srcs = srcs,
                    visibility = ["//visibility:public"],
                )

    pkg = native.package_name()  # e.g., "flow/designs/asap7/gcd"
    parts = pkg.split("/")

    if not platform and len(parts) >= 3:
        platform = parts[2]  # "asap7"
    if not design and len(parts) >= 4:
        design = parts[3]  # "gcd"

    key = "%s/%s" % (platform, design)
    if key not in designs:
        # Platform/design not in the parsed config set — skip silently.
        # This happens for platforms not listed in MODULE.bazel or when
        # the directory name doesn't match the DESIGN_NICKNAME in config.mk.
        return

    config = designs[key]
    name = config["name"]
    sources = _convert_sources(config["sources"], pkg)

    # Auto-detect rules-base.json if present in the package
    if "RULES_JSON" not in sources and native.glob(["rules-base.json"], allow_empty = True):
        sources["RULES_JSON"] = [":rules-base.json"]

    # Designs not tested in CI get tags = ["manual"] so they are excluded
    # from wildcard builds (bazel build //...) but can still be built explicitly.
    tags = [] if config.get("ci", False) else ["manual"]

    # Filter verilog_files: skip unresolved Make variables and invalid labels
    verilog_files = _filter_verilog_files(config["verilog_files"])

    # Collect extra data dependencies for VERILOG_INCLUDE_DIRS
    extra_data = _collect_include_dirs(config["arguments"])

    # Handle BLOCKS: create sub-macro orfs_flow() targets
    macros, lint_macros = _create_block_targets(
        config,
        designs,
        platform,
        design,
        pkg,
        tags,
        mock_openroad,
    )

    # Real flow — uses Docker image with real OpenROAD/Yosys
    parallel = NUM_CPUS if config["arguments"].get("SYNTH_HIERARCHICAL") == "1" else 0
    orfs_flow(
        name = name,
        verilog_files = verilog_files,
        pdk = "//flow:" + platform,
        arguments = config["arguments"],
        sources = sources,
        macros = macros if macros else [],
        stage_data = {"synth": extra_data} if extra_data else {},
        tags = tags,
        parallel_synth = parallel,
    )

    # Lint flow — fast validation with mock-openroad (only if configured)
    if mock_openroad:
        orfs_flow(
            name = name,
            verilog_files = verilog_files,
            pdk = "//flow:" + platform,
            arguments = config["arguments"],
            sources = sources,
            macros = lint_macros if lint_macros else [],
            stage_data = {"synth": extra_data} if extra_data else {},
            variant = "lint",
            lint = True,
            openroad = mock_openroad,
            tags = tags,
        )

def _filter_verilog_files(raw_verilog_files):
    """Filter verilog_files: skip unresolved Make variables and invalid labels."""
    verilog_files = []
    for vf in raw_verilog_files:
        if "$(" in vf or "${" in vf or "*" in vf or "))" in vf:
            continue
        if "//." in vf or vf.endswith(":"):
            continue
        if vf.endswith(":include") or "/include" in vf.split(":")[-1]:
            continue
        verilog_files.append(vf)
    return verilog_files

def _collect_include_dirs(arguments):
    """Collect extra data dependencies for VERILOG_INCLUDE_DIRS."""
    extra_data = []
    include_dirs = arguments.get("VERILOG_INCLUDE_DIRS", "")
    for inc_dir in include_dirs.replace("\t", " ").split(" "):
        inc_dir = inc_dir.strip().rstrip("/")
        if inc_dir:
            extra_data.append("//" + inc_dir + ":include")
    return extra_data

def _create_block_targets(config, designs, platform, design, pkg, tags, mock_openroad):
    """Create sub-macro orfs_flow() targets for BLOCKS.

    Returns:
        Tuple of (macros, lint_macros) where macros references real flow
        abstracts and lint_macros references lint flow abstracts.
    """
    macros = []
    lint_macros = []
    for block_name in config.get("blocks", []):
        block_key = "%s/%s" % (platform, "%s_%s" % (design, block_name))

        block_config = designs.get(block_key)
        if not block_config:
            continue

        block_verilog = [
            vf
            for vf in block_config["verilog_files"]
            if "$(" not in vf and "${" not in vf and "//." not in vf and not vf.endswith(":")
        ]
        block_sources = _convert_sources(block_config["sources"], pkg)

        # Real flow
        orfs_flow(
            name = block_config["name"],
            abstract_stage = "cts",
            verilog_files = block_verilog,
            pdk = "//flow:" + platform,
            arguments = block_config["arguments"],
            sources = block_sources,
            tags = tags,
        )
        macros.append(":%s_generate_abstract" % block_config["name"])

        # Lint flow (only if mock_openroad is configured)
        if mock_openroad:
            orfs_flow(
                name = block_config["name"],
                abstract_stage = "cts",
                verilog_files = block_verilog,
                pdk = "//flow:" + platform,
                arguments = block_config["arguments"],
                sources = block_sources,
                variant = "lint",
                lint = True,
                openroad = mock_openroad,
                tags = tags,
            )
            lint_macros.append(":%s_lint_generate_abstract" % block_config["name"])

    return macros, lint_macros
