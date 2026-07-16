"""Macro to create orfs_flow() targets from parsed config.mk data.

Call orfs_design() from a design's BUILD.bazel to auto-generate
orfs_flow() targets based on the design's config.mk:

    load("@orfs_designs//:designs.bzl", "orfs_design")
    orfs_design(config = "config.mk")

The orfs_designs repository rule (designs.bzl) must be instantiated
first to parse all config.mk files and generate the DESIGNS dict.
"""

load(
    "//private:blender.bzl",
    "blender_supports_pdk",
)
load(
    "//private:flow.bzl",
    "orfs_flow",
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

def orfs_design(name = None, config = "config.mk", platform = None, design = None, designs = None, mock_openroad = None, mock_yosys = None, user_arguments = [], user_sources = [], local_arguments = [], blender = False, extra = None):  # buildifier: disable=unused-variable
    """Create orfs_flow() targets for a design based on its parsed config.mk.

    Usage:

        load("@orfs_designs//:designs.bzl", "orfs_design")
        orfs_design(config = "config.mk")

    The platform and design are auto-detected from the package path
    (flow/designs/<platform>/<design>/).

    Args:
        name: Unused, required by Bazel macro convention.
        config: The config.mk file that drives this design.  Makes the
            BUILD file self-documenting about what configures the build.
        platform: Override platform (default: from package path).
        design: Override design nickname (default: from package path).
        designs: The DESIGNS dict from the orfs_designs repository rule.
            Supplied automatically by the generated wrapper in
            @orfs_designs//:designs.bzl.
        mock_openroad: Label for mock-openroad binary. When set, generates
            lint flow targets (variant="lint") alongside real flow targets.
            Example: "//mock/openroad/src/bin:openroad".
        mock_yosys: Label for mock-yosys binary. When set, lint flow uses
            this instead of real Yosys for synthesis.
            Example: "//mock/yosys/src/bin:yosys".
        user_arguments: List of variable names from config.mk that are
            project-specific (read by user-supplied .tcl/.mk, not by
            ORFS itself, e.g. FP_PDN_RAIL_OFFSET in a custom pdn.cfg).
            Routed through orfs_flow(user_arguments=...) to bypass the
            variables.yaml validator instead of being checked as known
            ORFS arguments.
        user_sources: List of source-typed variable names (vars in
            SOURCE_VARS) that are project-specific path hooks read only
            by user-supplied .tcl/.mk, not by ORFS itself (e.g. a
            per-design extra-SDC hook source'd from the design's own
            io.tcl). Routed through orfs_flow(user_sources=...) so the
            file is still staged into the sandbox, but the variable
            name bypasses the variables.yaml validator.
        local_arguments: List of variable names that are only used for
            $(VAR) expansion within the same config.mk and are not read
            by ORFS or by any user .tcl/.mk (e.g. VERILOG_FILES_BLACKBOX,
            which appears verbatim inside VERILOG_FILES). These are
            dropped entirely before orfs_flow() is invoked — neither
            validated against variables.yaml nor exposed as env vars.
        blender: if True, request the orfs_flow blender 3D-viewer targets
            for this design. Silently downgraded to False on PDKs that
            have no BlenderGDS stackup (see blender_supports_pdk in
            private/blender.bzl), so callers can flip this on globally
            without having to enumerate supported PDKs.
        extra: optional callable invoked after the real flow with the
            fully-processed design data (name, platform, verilog_files,
            arguments, user_arguments, sources, user_sources, macros,
            stage_data, tags) so callers can attach additional
            per-design targets (extra flow variants, reporting targets)
            without orfs_design knowing their policy.
    """
    if designs == None:
        fail("orfs_design() requires designs: load orfs_design from @orfs_designs//:designs.bzl")

    # Validate that the config file exists in this package
    if not native.glob([config], allow_empty = True):
        fail("orfs_design(): config file %s not found in %s" % (config, native.package_name()))

    # Create filegroups for design files so they are accessible to
    # orfs_flow() rules without using exports_files().
    existing_rules = native.existing_rules()
    for fg_name, fg_glob in [
        ("design_config", ["*.mk", "*.sdc", "*.json", "*.cfg", "*.tcl", "*.def"]),
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

    # Derive the DESIGNS lookup key from the package path by stripping
    # the "flow/designs/" prefix.  For block sub-packages like
    # "flow/designs/asap7/parent/block", the resulting key won't match
    # any DESIGNS entry, so orfs_design() becomes a no-op (block targets
    # are created by the parent's _create_block_targets()).
    prefix = "flow/designs/"
    if platform or design:
        # Explicit overrides — fall back to positional extraction
        parts = pkg.split("/")
        if not platform and len(parts) >= 3:
            platform = parts[2]
        if not design and len(parts) >= 4:
            design = parts[3]
        key = "%s/%s" % (platform, design)
    elif pkg.startswith(prefix):
        key = pkg[len(prefix):]
    else:
        return

    if key not in designs:
        # Platform/design not in the parsed config set — skip silently.
        # This happens for platforms not listed in MODULE.bazel, when
        # the directory name doesn't match the DESIGN_NICKNAME in config.mk,
        # or for block sub-packages (handled by the parent design).
        return

    config = designs[key]
    platform = config["platform"]
    name = config["name"]

    # Design directory name — used for block key construction in
    # _create_block_targets().  Derived from the key after the platform prefix.
    design = key[len(platform) + 1:] if key.startswith(platform + "/") else key
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
        mock_yosys,
    )

    # Real flow — uses Docker image with real OpenROAD/Yosys
    arguments = dict(config["arguments"])

    # Drop caller-flagged local helper vars used only via $(VAR)
    # expansion within the same config.mk (e.g. VERILOG_FILES_BLACKBOX).
    # They must not reach orfs_flow — they would either fail validation
    # or be exposed as noise env vars. The config.mk parser may classify
    # such helpers as either arguments or sources (e.g. when they expand
    # to file globs), so drop from both.
    for var in local_arguments:
        arguments.pop(var, None)
        sources.pop(var, None)

    # Move caller-flagged design-specific knobs out of arguments and into
    # user_arguments so they bypass the variables.yaml validator.
    user_args = {}
    for var in user_arguments:
        if var in arguments:
            user_args[var] = arguments.pop(var)

    # Same idea for source-typed (path-label) project-specific knobs:
    # variables that are in SOURCE_VARS (so the parser staged the path
    # as a label) but are read only by user .tcl/.mk and have no
    # variables.yaml entry.
    user_srcs = {}
    for var in user_sources:
        if var in sources:
            user_srcs[var] = sources.pop(var)

    # Default SYNTH_NUM_PARTITIONS to a static value so that the action graph
    # is identical across machines and remote cache hits are possible.  Users
    # who prefer local parallelism over caching can pass NUM_CPUS explicitly.
    if arguments.get("SYNTH_HIERARCHICAL") == "1":
        if "SYNTH_NUM_PARTITIONS" not in arguments:
            keep_modules = arguments.get("SYNTH_KEEP_MODULES", "")
            if keep_modules:
                arguments["SYNTH_NUM_PARTITIONS"] = str(len(keep_modules.split()))
            else:
                arguments["SYNTH_NUM_PARTITIONS"] = "32"

    orfs_flow(
        name = name,
        verilog_files = verilog_files,
        pdk = "//flow:" + platform,
        arguments = arguments,
        user_arguments = user_args,
        sources = sources,
        user_sources = user_srcs,
        macros = macros if macros else [],
        stage_data = {"synth": extra_data} if extra_data else {},
        tags = tags,
        blender = blender and blender_supports_pdk("//flow:" + platform),
    )

    # Caller extension hook: invoked with the fully-processed design data
    # (labels converted, local/user arguments routed) so consumers can
    # attach additional per-design targets — e.g. ORFS's OpenROAD-SYN
    # status flows — without teaching orfs_design about their policy.
    if extra:
        extra(
            name = name,
            platform = platform,
            verilog_files = verilog_files,
            arguments = arguments,
            user_arguments = user_args,
            sources = sources,
            user_sources = user_srcs,
            macros = macros if macros else [],
            stage_data = {"synth": extra_data} if extra_data else {},
            tags = tags,
        )

    # Lint flow — fast validation with mock-openroad (only if configured)
    if mock_openroad:
        lint_kwargs = dict(
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
        if mock_yosys:
            lint_kwargs["yosys"] = mock_yosys
        orfs_flow(**lint_kwargs)

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

def _create_block_targets(config, designs, platform, design, pkg, tags, mock_openroad, mock_yosys = None):
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
            lint_kwargs = dict(
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
            if mock_yosys:
                lint_kwargs["yosys"] = mock_yosys
            orfs_flow(**lint_kwargs)
            lint_macros.append(":%s_lint_generate_abstract" % block_config["name"])

    return macros, lint_macros
