"""Parser for ORFS config.mk design DSL files.

Parses config.mk files and produces structured data suitable for generating
orfs_flow() Bazel targets. Supports all DSL features found across the 84
config.mk files, with deprecation warnings for features that should be
migrated.

Usage:
    python3 config_mk_parser.py [--lint] [--json] <config.mk> [<config.mk> ...]
    python3 config_mk_parser.py --all <designs_dir>
"""

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


# Variables that map to orfs_flow() structural params (not arguments dict)
STRUCTURAL_VARS = {
    "PLATFORM",
    "DESIGN_NAME",
    "DESIGN_NICKNAME",
    "VERILOG_FILES",
    "SDC_FILE",
    "SRC_HOME",
    "BLOCKS",
}

# Variables that map to orfs_flow() sources dict (file references)
SOURCE_VARS = {
    "SDC_FILE",
    "FASTROUTE_TCL",
    "IO_CONSTRAINTS",
    "MACRO_PLACEMENT_TCL",
    "PDN_TCL",
    "TAPCELL_TCL",
    "FLOORPLAN_DEF",
    "SEAL_GDS",
    "ADDITIONAL_LEFS",
    "ADDITIONAL_LIBS",
    "ADDITIONAL_SLOW_LIBS",
    "ADDITIONAL_FAST_LIBS",
    "ADDITIONAL_TYP_LIBS",
    "ADDITIONAL_GDS",
    "SYNTH_NETLIST_FILES",
    "VERILOG_FILES_BLACKBOX",
    # VERILOG_INCLUDE_DIRS are directories, not files — treat as arguments
    # "VERILOG_INCLUDE_DIRS",
    "WRAP_LEFS",
    "WRAP_LIBS",
    "SYNTH_CANONICALIZE_TCL",
    "FOOTPRINT_TCL",
    "SDC_FILE_EXTRA",
    "SC_LEF",
    # AUTO_MEMORIES: user-supplied .memories files merged onto what the
    # scanner detects. gen_memories.py reads them by path during
    # canonicalization, so they have to be staged like any other source
    # rather than passed as a string.
    "ADDITIONAL_MEMORIES",
}

# Variables that are purely for path resolution, not passed to orfs_flow()
PATH_ONLY_VARS = {
    "DESIGN_NICKNAME",
    "SRC_HOME",
    "TEMP_DESIGN_DIR",
    "TOP_DESIGN_NICKNAME",
}

# Variables that are structural but not arguments
NON_ARGUMENT_VARS = STRUCTURAL_VARS | PATH_ONLY_VARS

# Deprecated variable references that emit lint warnings
DEPRECATED_REFS = {
    "SRC_HOME": "use $(DESIGN_HOME)/src/$(DESIGN_NICKNAME) instead",
    "WORK_HOME": "use previous_stage in orfs_flow() instead",
    "TOP_DESIGN_NICKNAME": "use explicit parent path instead",
}


@dataclass
class Warning:
    """A lint warning about a deprecated or unsupported DSL feature."""

    line_number: int
    message: str
    category: str  # "deprecated", "unsupported", "info"


@dataclass
class ParsedDesign:
    """Result of parsing a config.mk file."""

    config_path: str  # Path to the config.mk file
    platform: str = ""  # e.g., "asap7"
    design_name: str = ""  # DESIGN_NAME value
    design_nickname: str = ""  # DESIGN_NICKNAME (or dir name default)
    verilog_files: list = field(default_factory=list)  # Bazel labels
    sources: dict = field(default_factory=dict)  # var -> [labels]
    arguments: dict = field(default_factory=dict)  # var -> value
    blocks: list = field(default_factory=list)  # BLOCKS list
    block_configs: list = field(default_factory=list)  # Parsed sub-macros
    has_conditionals: bool = False
    warnings: list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d["warnings"] = [
            asdict(w) if isinstance(w, Warning) else w for w in self.warnings
        ]
        d["block_configs"] = [
            bc.to_dict() if isinstance(bc, ParsedDesign) else bc
            for bc in self.block_configs
        ]
        return d


def _join_continuation_lines(lines):
    """Join lines ending with backslash continuation."""
    result = []
    current = ""
    current_start_line = 0
    for i, line in enumerate(lines):
        if not current:
            current_start_line = i
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            current += stripped[:-1]
        else:
            current += stripped
            result.append((current_start_line, current))
            current = ""
    if current:
        result.append((current_start_line, current))
    return result


def _strip_inline_comment(value):
    """Remove inline comments from a value, being careful with # in strings."""
    # Simple heuristic: # preceded by whitespace is a comment
    # This handles most cases without full Make parsing
    match = re.search(r"\s#\s", value)
    if match:
        return value[: match.start()].rstrip()
    # Also handle # at start of remaining value after whitespace
    match = re.search(r"\s#[^(]", value)
    if match:
        return value[: match.start()].rstrip()
    return value


class ConfigMkParser:
    """Parser for ORFS config.mk design DSL files."""

    def __init__(self, designs_home="flow/designs", flow_home="flow"):
        self.designs_home = designs_home
        self.flow_home = flow_home

    def parse(self, config_path, base_dir=None, overrides=None):
        """Parse a config.mk file and return a ParsedDesign.

        Args:
            config_path: Path to the config.mk file.
            base_dir: Base directory for resolving relative include paths.
                      Defaults to the directory containing config_path.
            overrides: Optional dict of structural-var overrides applied
                      after file parsing. Used by the shared-block.mk
                      BLOCKS path to pin DESIGN_NAME / DESIGN_NICKNAME per
                      block (mirrors make's GENERATE_ABSTRACT_RULE).

        Returns:
            ParsedDesign with all parsed information.
        """
        config_path = str(config_path)
        if base_dir is None:
            base_dir = os.path.dirname(config_path)

        # Derive platform and design dir from path
        # Expected: .../flow/designs/<platform>/<design>/config.mk
        # Or: .../flow/designs/<platform>/<design>/<block>/config.mk
        parts = Path(config_path).parts
        platform = ""
        design_dir_name = ""
        try:
            designs_idx = parts.index("designs")
            if designs_idx + 2 < len(parts):
                platform = parts[designs_idx + 1]
                design_dir_name = parts[designs_idx + 2]
        except (ValueError, IndexError):
            pass

        result = ParsedDesign(config_path=config_path)
        raw_vars = {}  # var_name -> (value, assignment_op, line_number)

        self._parse_file(config_path, base_dir, raw_vars, result, set())

        # Set platform from parsed or derived
        if "PLATFORM" in raw_vars:
            result.platform = raw_vars["PLATFORM"][0].strip()
        elif platform:
            result.platform = platform

        # Set design_name
        if "DESIGN_NAME" in raw_vars:
            result.design_name = raw_vars["DESIGN_NAME"][0].strip()

        # Set design_nickname (defaults to design dir name).
        # Resolve variable references (e.g. ${TOP_DESIGN_NICKNAME}_${DESIGN_NAME})
        # using already-known structural values.
        if "DESIGN_NICKNAME" in raw_vars:
            nickname_raw = raw_vars["DESIGN_NICKNAME"][0].strip()
            if "$" in nickname_raw:
                early_ctx = {
                    "DESIGN_NAME": result.design_name,
                    "PLATFORM": result.platform,
                }
                if "TOP_DESIGN_NICKNAME" in raw_vars:
                    early_ctx["TOP_DESIGN_NICKNAME"] = raw_vars["TOP_DESIGN_NICKNAME"][
                        0
                    ].strip()
                nickname_raw = self._resolve_simple_refs(nickname_raw, early_ctx)
            result.design_nickname = nickname_raw
        elif design_dir_name:
            result.design_nickname = design_dir_name
        elif result.design_name:
            result.design_nickname = result.design_name

        # Apply caller-supplied overrides to structural vars. Used by the
        # shared-block.mk BLOCKS path below to parameterise the same
        # block.mk for each entry of BLOCKS=, mirroring make's
        # flow/Makefile GENERATE_ABSTRACT_RULE second branch.
        if overrides:
            if "DESIGN_NAME" in overrides:
                result.design_name = overrides["DESIGN_NAME"]
            if "DESIGN_NICKNAME" in overrides:
                result.design_nickname = overrides["DESIGN_NICKNAME"]

        # Check structural vars for deprecated patterns
        for var_name in ("DESIGN_NICKNAME", "DESIGN_NAME", "PLATFORM"):
            if var_name in raw_vars:
                raw_val = raw_vars[var_name][0]
                line_n = raw_vars[var_name][2]
                if re.search(r"\$\{[A-Za-z_]", raw_val):
                    result.warnings.append(
                        Warning(
                            line_number=line_n,
                            message="${VAR} shell-style syntax: "
                            "use $(VAR) Make-style",
                            category="deprecated",
                        )
                    )

        # Emit deferred warnings for variables only set in conditionals.
        # These are variables that never got a value from a default branch,
        # so they will be absent in the Bazel build.
        for var_name, ln in getattr(result, "_conditional_only_vars", {}).items():
            if var_name not in raw_vars:
                result.warnings.append(
                    Warning(
                        line_number=ln,
                        message=f"{var_name}: only set inside conditional, "
                        "will be missing in Bazel build",
                        category="info",
                    )
                )

        # Build variable resolution context
        ctx = self._build_context(result, config_path, raw_vars)

        # Process each variable
        for var_name, (value, op, line_num) in raw_vars.items():
            if var_name in ("PLATFORM", "DESIGN_NAME", "DESIGN_NICKNAME"):
                continue
            if var_name in PATH_ONLY_VARS:
                continue

            resolved = self._resolve_refs(value.strip(), ctx, result, line_num)

            if var_name == "VERILOG_FILES":
                result.verilog_files = self._map_verilog_files(
                    resolved, ctx, result, line_num
                )
            elif var_name == "BLOCKS":
                result.blocks = resolved.split()
            elif var_name in SOURCE_VARS:
                labels = self._map_source_file(
                    var_name, resolved, ctx, result, line_num
                )
                if labels:
                    result.sources[var_name] = labels
            elif var_name not in NON_ARGUMENT_VARS:
                result.arguments[var_name] = resolved

        # A hierarchical parent's platform config.mk may branch on
        # BLOCKS.  Adopt what that branch changes; see
        # _apply_platform_blocks_vars.
        if result.blocks:
            self._apply_platform_blocks_vars(result, config_path, raw_vars, ctx)

        # Process BLOCKS — discover and parse sub-macro configs.
        if result.blocks:
            config_dir = os.path.dirname(config_path)
            shared_block_mk = os.path.join(config_dir, "block.mk")
            for block_name in result.blocks:
                # Path 1: per-block config.mk in a sub-directory.
                block_config = os.path.join(config_dir, block_name, "config.mk")
                if os.path.exists(block_config):
                    block_parsed = self.parse(block_config)
                    result.block_configs.append(block_parsed)
                    continue
                # Path 2: shared block.mk parameterised by DESIGN_NAME.
                # Matches make's flow/Makefile GENERATE_ABSTRACT_RULE
                # second branch:
                #     $(MAKE) DESIGN_NAME=<block> \
                #             DESIGN_NICKNAME=<parent>_<block> \
                #             DESIGN_CONFIG=<parent_dir>/block.mk \
                #             generate_abstract
                if os.path.exists(shared_block_mk):
                    block_parsed = self.parse(
                        shared_block_mk,
                        overrides={
                            "DESIGN_NAME": block_name,
                            "DESIGN_NICKNAME": f"{result.design_nickname}_{block_name}",
                        },
                    )
                    result.block_configs.append(block_parsed)

        return result

    def _apply_platform_blocks_vars(self, result, config_path, raw_vars, ctx):
        """Adopt platform config.mk variables that branch on BLOCKS.

        BLOCKS is a make-only concept: flow/Makefile turns it into the
        per-block abstract rules, so it is not a flow variable and
        bazel-orfs never exports it.  A platform config.mk can still
        branch on it, and asap7 does:

            ifeq ($(BLOCKS),)
               export PDN_TCL ?= $(PLATFORM_DIR)/openRoad/pdn/grid_strategy-M1-M2-M5-M6.tcl
            else
               export PDN_TCL ?= $(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl
            endif

        make includes the platform config.mk after the design's, with
        BLOCKS set, so a hierarchical parent gets the BLOCKS grid -- a
        core ring, an ElementGrid over the macros and M5-M6 macro
        connects.  Inside a bazel action BLOCKS is empty, so the same
        include silently picks the flat grid instead.

        Resolved here rather than by exporting BLOCKS: exporting it
        would also wake flow/Makefile's own BLOCKS machinery
        (BLOCK_LEFS/BLOCK_TYP_LIBS appended to ADDITIONAL_LEFS/LIBS as
        make-relative results/ paths that do not exist in the sandbox),
        and BLOCKS has no `stages:` entry in variables.yaml.

        The platform file is parsed twice, once with BLOCKS empty and
        once with it set, and only the variables whose value actually
        differs are adopted -- and only where the design has not set
        them itself, matching the platform's `?=`.

        Args:
            result: ParsedDesign being built; mutated in place.
            config_path: path of the design's config.mk.
            raw_vars: the design's own assignments, var -> (value, op, line).
            ctx: variable-resolution context for this design.
        """
        platform_config = self._platform_config_path(config_path, result.platform)
        if not platform_config or not os.path.exists(platform_config):
            return

        base_dir = os.path.dirname(platform_config)
        without = {}
        with_blocks = {"BLOCKS": (" ".join(result.blocks), "=", 0)}
        for seed in (without, with_blocks):
            # A throwaway ParsedDesign: the platform file's warnings
            # belong to the platform, not to this design.
            self._parse_file(
                platform_config, base_dir, seed, ParsedDesign(config_path=""), set()
            )

        for var_name in sorted(with_blocks):
            if var_name == "BLOCKS" or var_name in NON_ARGUMENT_VARS:
                continue
            if var_name in raw_vars:
                # The design set it: the platform's `?=` never fires.
                continue
            new_value = with_blocks[var_name][0]
            if var_name in without and without[var_name][0] == new_value:
                continue

            resolved = self._resolve_refs(new_value.strip(), ctx, result, 0)
            if var_name in SOURCE_VARS:
                labels = self._map_source_file(var_name, resolved, ctx, result, 0)
                if labels:
                    result.sources[var_name] = labels
            else:
                result.arguments[var_name] = resolved

    @staticmethod
    def _platform_config_path(config_path, platform):
        """flow/platforms/<platform>/config.mk next to flow/designs/..."""
        if not platform:
            return None
        parts = Path(config_path).parts
        try:
            designs_idx = len(parts) - 1 - parts[::-1].index("designs")
        except ValueError:
            return None
        flow_dir = Path(*parts[:designs_idx]) if designs_idx else Path(".")
        return str(flow_dir / "platforms" / platform / "config.mk")

    def _parse_file(self, filepath, base_dir, raw_vars, result, visited):
        """Parse a single file, handling includes recursively."""
        filepath = os.path.abspath(filepath)
        if filepath in visited:
            return
        visited.add(filepath)

        if not os.path.exists(filepath):
            result.warnings.append(
                Warning(
                    line_number=0,
                    message=f"File not found: {filepath}",
                    category="error",
                )
            )
            return

        with open(filepath) as f:
            lines = f.readlines()

        joined = _join_continuation_lines(lines)

        # One frame per open conditional, innermost last.  A frame is
        # either DECIDED -- make's outcome is knowable from the values
        # parsed so far, so the taken branch is known exactly -- or
        # UNDECIDED, where the historical heuristic applies: the
        # if-branch of `ifeq ($(VAR),)` is the default (Make variables
        # are empty unless set) and nothing else is.
        frames = []

        for line_num, line in joined:
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            # Handle conditionals
            if re.match(r"^(ifeq|ifneq|ifdef|ifndef)\b", stripped):
                if not frames:
                    result.has_conditionals = True
                    self._warn_conditional(stripped, line_num + 1, result)
                frames.append(self._open_frame(stripped, raw_vars, len(frames)))
                continue

            if stripped.startswith("else"):
                if frames:
                    self._else_frame(stripped, raw_vars, frames)
                    if re.match(r"^else\s+(ifeq|ifneq|ifdef|ifndef)\b", stripped):
                        self._warn_conditional(stripped, line_num + 1, result)
                continue

            if stripped == "endif":
                if frames:
                    frames.pop()
                continue

            # Inside conditionals: accept an assignment only from the
            # branch make would take (decided frames), or from the
            # heuristic default branch (undecided frames).
            if frames:
                accept = all(f["accepts"] for f in frames)
                known_dead = any(f["decided"] and not f["taken"] for f in frames)
                self._parse_assignment(
                    stripped,
                    line_num,
                    raw_vars,
                    result,
                    conditional=not accept,
                    # A branch make provably skips is not a variable that
                    # "will be missing in Bazel" -- it is missing in make
                    # too, so there is nothing to warn about.
                    record_conditional_only=not known_dead,
                )
                continue

            # Handle include directives
            include_match = re.match(r"^-?include\s+(.+)", stripped)
            if include_match:
                include_path = include_match.group(1).strip()
                result.warnings.append(
                    Warning(
                        line_number=line_num + 1,
                        message=f"include directive: consider inlining the included content",
                        category="deprecated",
                    )
                )
                # Resolve include path
                resolved_path = self._resolve_include_path(include_path, base_dir)
                if resolved_path:
                    self._parse_file(
                        resolved_path,
                        os.path.dirname(resolved_path),
                        raw_vars,
                        result,
                        visited,
                    )
                continue

            # Handle Make target lines (not DSL)
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*:", stripped) and "=" not in stripped:
                result.warnings.append(
                    Warning(
                        line_number=line_num + 1,
                        message=f"Make target in config: move to Makefile",
                        category="deprecated",
                    )
                )
                continue

            # Skip Make recipe lines (tab-indented)
            if line.startswith("\t"):
                continue

            # Parse export assignments
            self._parse_assignment(
                stripped, line_num, raw_vars, result, conditional=False
            )

    # ------------------------------------------------------------------
    # Make conditionals
    #
    # The parser evaluates a conditional whenever the outcome is
    # knowable: every variable the test references has already been
    # assigned in this parse (the file itself or a file that included
    # it).  That is not a cosmetic improvement.  asap7/riscv32i-mock-sram
    # sets BLOCKS= and then includes asap7/riscv32i/config.mk, whose
    #
    #     ifeq ($(BLOCKS),)
    #         export ADDITIONAL_LEFS = $(PLATFORM_DIR)/lef/fakeram7_256x32.lef
    #         export ADDITIONAL_LIBS = $(PLATFORM_DIR)/lib/NLDM/fakeram7_256x32.lib
    #     endif
    #
    # branch is exactly the branch make skips -- the platform's canned
    # fakeram abstract is for the NON-hierarchical build; the
    # hierarchical one builds its own.  Assuming the if-branch handed
    # the parent both.
    #
    # When a referenced variable is unknown -- set by the platform
    # config.mk, variables.mk, the environment or the command line, none
    # of which this parser reads -- the historical heuristic stands: the
    # if-branch of `ifeq ($(VAR),)` is the default, because an unset Make
    # variable is empty, and no other branch is.
    # ------------------------------------------------------------------

    def _open_frame(self, directive, raw_vars, depth):
        """Build the frame for a newly opened conditional."""
        # `ifeq ($(VAR),)` tests for empty: its if-branch is the
        # heuristic default, since an unset Make variable is empty.
        test_empty = bool(
            re.match(r"^ifeq\s+\(\$[\({].*[\)}]\s*,\s*\)", directive)
        )
        outcome = self._eval_conditional(directive, raw_vars)
        frame = {
            "test_empty": test_empty,
            "decided": outcome is not None,
            "taken": bool(outcome),
            "seen_taken": bool(outcome),
            # Only the outermost conditional ever had a "default branch";
            # assignments nested deeper were never adopted on a guess.
            "heur_default": test_empty and depth == 0,
            "depth": depth,
        }
        self._set_accepts(frame)
        return frame

    def _else_frame(self, directive, raw_vars, frames):
        """Advance the innermost frame onto its `else` / `else ifeq` arm."""
        frame = frames[-1]
        chained = re.match(r"^else\s+(ifeq|ifneq|ifdef|ifndef)\b", directive)
        if chained:
            outcome = None
            if not frame["seen_taken"]:
                outcome = self._eval_conditional(
                    directive[len("else") :].strip(), raw_vars
                )
            if frame["seen_taken"]:
                # An earlier arm already matched: make skips this one.
                frame["decided"] = True
                frame["taken"] = False
            elif outcome is None:
                frame["decided"] = False
                frame["taken"] = False
            else:
                frame["decided"] = True
                frame["taken"] = bool(outcome)
                frame["seen_taken"] = frame["seen_taken"] or bool(outcome)
            # A chained arm is never the heuristic default.
            frame["heur_default"] = False
        elif frame["decided"]:
            # Plain else on a decided frame: taken iff nothing matched.
            frame["taken"] = not frame["seen_taken"]
            frame["seen_taken"] = True
        else:
            # Plain else on an undecided frame: the historical default,
            # unless the if-branch already claimed it.
            frame["heur_default"] = not frame["test_empty"] and frame["depth"] == 0
        self._set_accepts(frame)

    @staticmethod
    def _set_accepts(frame):
        frame["accepts"] = (
            frame["taken"] if frame["decided"] else frame["heur_default"]
        )

    def _eval_conditional(self, directive, raw_vars):
        """Evaluate a Make conditional; None when the outcome is unknown.

        Args:
            directive: the conditional text, e.g. `ifeq ($(BLOCKS),)`.
            raw_vars: var -> (value, op, line) parsed so far.

        Returns:
            True if make would take this branch, False if it would skip
            it, None if any variable the test references is unknown here.
        """
        match = re.match(r"^(ifeq|ifneq|ifdef|ifndef)\s+(.*)$", directive.strip())
        if not match:
            return None
        kind, rest = match.group(1), match.group(2).strip()

        if kind in ("ifdef", "ifndef"):
            name = rest.split()[0] if rest.split() else ""
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
                return None
            if name not in raw_vars:
                # Could be set anywhere this parser does not read.
                return None
            defined = bool(raw_vars[name][0].strip())
            return defined if kind == "ifdef" else not defined

        args = self._split_condition_args(rest)
        if args is None:
            return None
        left, right = (self._expand_known(a, raw_vars) for a in args)
        if left is None or right is None:
            return None
        equal = left.strip() == right.strip()
        return equal if kind == "ifeq" else not equal

    @staticmethod
    def _split_condition_args(rest):
        """Split an ifeq/ifneq argument list into its two sides.

        Handles both `(a,b)` and `"a" "b"` spellings; returns None for
        anything else, including a comma nested inside a $(...) call.
        """
        if rest.startswith("(") and rest.endswith(")"):
            inner = rest[1:-1]
            depth = 0
            for i, ch in enumerate(inner):
                if ch in "({":
                    depth += 1
                elif ch in ")}":
                    depth -= 1
                elif ch == "," and depth == 0:
                    return inner[:i], inner[i + 1 :]
            return None
        quoted = re.findall(r'"([^"]*)"|\'([^\']*)\'', rest)
        if len(quoted) == 2:
            return tuple(a or b for a, b in quoted)
        return None

    def _expand_known(self, text, raw_vars):
        """Expand $(VAR)/${VAR} from raw_vars; None if anything is left.

        Deliberately strict: a reference this parser cannot resolve, or
        any Make function call, makes the whole conditional unknown
        rather than silently comparing against a literal `$(...)`.
        """
        seen = set()
        value = text
        for _ in range(8):
            refs = re.findall(
                r"\$\(([A-Za-z_][A-Za-z0-9_]*)\)|\$\{([A-Za-z_][A-Za-z0-9_]*)\}",
                value,
            )
            names = [a or b for a, b in refs]
            if not names:
                break
            if any(n not in raw_vars for n in names):
                return None
            if any(n in seen for n in names):
                return None
            seen.update(names)
            ctx = {n: raw_vars[n][0].strip() for n in names}
            value = self._resolve_simple_refs(value, ctx)
        if "$" in value:
            return None
        return value

    def _parse_assignment(
        self,
        line,
        line_num,
        raw_vars,
        result,
        conditional=False,
        record_conditional_only=True,
    ):
        """Parse an export VAR = value line."""
        # Match: export VAR = value, export VAR ?= value, export VAR := value
        # Also: VAR = value (without export), and export VAR=value (no spaces)
        match = re.match(
            r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_.]*)\s*(\+=|\?=|:=|=)\s*(.*)",
            line,
        )
        if not match:
            return

        var_name = match.group(1)
        op = match.group(2)
        value = match.group(3).strip()
        value = _strip_inline_comment(value)

        # For ?= only set if not already defined
        if op == "?=" and var_name in raw_vars and not conditional:
            return

        # Skip non-default conditional assignments — the parser can't
        # evaluate Make conditionals, so extracting values from unknown
        # branches produces wrong configs. Warnings are deferred to
        # _check_conditional_warnings() after all branches are processed.
        if conditional:
            if (
                record_conditional_only
                and var_name not in raw_vars
                and var_name not in NON_ARGUMENT_VARS
            ):
                result._conditional_only_vars = getattr(
                    result, "_conditional_only_vars", {}
                )
                result._conditional_only_vars.setdefault(var_name, line_num + 1)
            return

        # For += append to existing value
        if op == "+=" and var_name in raw_vars:
            prev_value, prev_op, prev_line = raw_vars[var_name]
            raw_vars[var_name] = (prev_value + " " + value, prev_op, prev_line)
        else:
            raw_vars[var_name] = (value, op, line_num + 1)

    def _build_context(self, result, config_path, raw_vars):
        """Build the variable resolution context."""
        config_dir = os.path.dirname(config_path)

        # Determine design_dir relative path from the designs_home
        # e.g., "flow/designs/asap7/gcd"
        try:
            rel_config_dir = str(
                Path(config_dir).relative_to(
                    Path(config_path).parents[len(Path(config_path).parts) - 1]
                )
            )
        except (ValueError, IndexError):
            rel_config_dir = config_dir

        ctx = {
            "DESIGN_HOME": self.designs_home,
            "PLATFORM": result.platform,
            "DESIGN_NAME": result.design_name,
            "DESIGN_NICKNAME": result.design_nickname,
            "DESIGN_DIR": f"{self.designs_home}/{result.platform}/{result.design_nickname}",
            "PLATFORM_DIR": f"{self.flow_home}/platforms/{result.platform}",
            "FLOW_HOME": self.flow_home,
            "_config_dir": config_dir,
            "_rel_config_dir": rel_config_dir,
        }

        # Add SRC_HOME if defined
        if "SRC_HOME" in raw_vars:
            src_home_val = raw_vars["SRC_HOME"][0].strip()
            # Resolve SRC_HOME itself
            ctx["SRC_HOME"] = self._resolve_refs(src_home_val, ctx, None, 0)
        else:
            ctx["SRC_HOME"] = f"{self.designs_home}/src/{result.design_nickname}"

        # Add any custom variables (like TOP_DESIGN_NICKNAME)
        for var_name in ("TOP_DESIGN_NICKNAME",):
            if var_name in raw_vars:
                val = raw_vars[var_name][0].strip()
                ctx[var_name] = self._resolve_refs(val, ctx, None, 0)

        # Add VERILOG_FILES_BLACKBOX to context so it can be substituted
        # inside VERILOG_FILES wildcard expressions
        if "VERILOG_FILES_BLACKBOX" in raw_vars:
            val = raw_vars["VERILOG_FILES_BLACKBOX"][0].strip()
            ctx["VERILOG_FILES_BLACKBOX"] = self._resolve_refs(val, ctx, None, 0)

        return ctx

    def _resolve_refs(self, value, ctx, result, line_num):
        """Resolve Make variable references in a value string.

        Handles both $(VAR) and ${VAR} syntax.
        """
        if not value:
            return value

        # Check for deprecated ${VAR} syntax
        if result and re.search(r"\$\{[A-Za-z_]", value):
            result.warnings.append(
                Warning(
                    line_number=line_num,
                    message="${VAR} shell-style syntax: use $(VAR) Make-style",
                    category="deprecated",
                )
            )

        # Check for deprecated variable references
        if result:
            for dep_var, msg in DEPRECATED_REFS.items():
                if f"$({dep_var})" in value or f"${{{dep_var}}}" in value:
                    result.warnings.append(
                        Warning(
                            line_number=line_num,
                            message=f"$({dep_var}): {msg}",
                            category="deprecated",
                        )
                    )

        # Check for $(if ...), $(strip ...), $(filter ...), $(and ...) functions
        if result:
            for func in ("if", "strip", "filter", "filter-out", "and"):
                if f"$({func} " in value or f"$({func}\t" in value:
                    result.warnings.append(
                        Warning(
                            line_number=line_num,
                            message=f"$({func} ...): simplify or move complexity to platform config",
                            category="deprecated",
                        )
                    )

        # Handle $(sort $(wildcard ...)) pattern
        sort_wildcard = re.match(
            r"^\$\(sort\s+\$\(wildcard\s+(.+?)\)\s*\)$", value.strip()
        )
        if sort_wildcard:
            return f"$(sort $(wildcard {self._resolve_simple_refs(sort_wildcard.group(1), ctx)}))"

        # Handle $(wildcard ...) pattern
        wildcard = re.match(r"^\$\(wildcard\s+(.+?)\)$", value.strip())
        if wildcard:
            return f"$(wildcard {self._resolve_simple_refs(wildcard.group(1), ctx)})"

        # Handle $(sort $(filter-out ...))
        filter_out = re.match(
            r"^\$\(sort\s+\$\(filter-out\s+(.+?),\s*\$\(wildcard\s+(.+?)\)\s*\)\s*\)$",
            value.strip(),
        )
        if filter_out:
            resolved_glob = self._resolve_simple_refs(filter_out.group(2), ctx)
            return f"$(sort $(filter-out {filter_out.group(1)}, $(wildcard {resolved_glob})))"

        # Handle $(if ...) — extract a reasonable default
        if_match = re.match(r"^\$\(if\s+", value.strip())
        if if_match:
            # For $(if) expressions, we can't resolve statically
            # Return the raw value — it will be handled by the caller
            return self._resolve_simple_refs(value, ctx)

        # Handle $(strip ...) — unwrap
        strip_match = re.match(r"^\$\(strip\s+(.*)\)$", value.strip())
        if strip_match:
            inner = strip_match.group(1).strip()
            return self._resolve_refs(inner, ctx, result, line_num)

        # Simple variable resolution
        return self._resolve_simple_refs(value, ctx)

    def _resolve_simple_refs(self, value, ctx):
        """Replace $(VAR) and ${VAR} with their values from context."""

        def replace_var(match):
            var_name = match.group(1) or match.group(2)
            if var_name in ctx:
                return ctx[var_name]
            return match.group(0)  # Leave unresolved

        # Replace $(VAR) and ${VAR} patterns (only simple variable refs)
        result = re.sub(
            r"\$\(([A-Za-z_][A-Za-z0-9_]*)\)|\$\{([A-Za-z_][A-Za-z0-9_]*)\}",
            replace_var,
            value,
        )
        return result

    def _map_verilog_files(self, resolved, ctx, result, line_num):
        """Map resolved VERILOG_FILES value to Bazel labels."""
        labels = []

        # Handle $(sort $(wildcard <path>/*.v)) or $(sort $(wildcard <path>/*.sv))
        # Supports multiple paths: $(sort $(wildcard dir1/*.v dir2/*.v))
        sort_wc_match = re.match(
            r"^\$\(sort\s+\$\(wildcard\s+(.+)\)\s*\)$", resolved.strip()
        )
        if sort_wc_match:
            inner = sort_wc_match.group(1).strip()
            glob_labels = []
            for part in inner.split():
                gm = re.match(r"^(.+)/\*\.(v|sv|svh)$", part.strip())
                if gm:
                    glob_labels.append(self._dir_to_verilog_label(gm.group(1)))
            if glob_labels:
                return glob_labels

        # Handle $(wildcard <path>/*.v) without sort
        wc_match = re.match(
            r"^\$\(wildcard\s+(.+?)/\*\.(v|sv)\s*\)\s*$", resolved.strip()
        )
        if wc_match:
            dir_path = wc_match.group(1)
            label = self._dir_to_verilog_label(dir_path)
            return [label]

        # Handle bare glob pattern (no $(wildcard)): path/*.v
        bare_glob = re.match(r"^(.+?)/\*\.(v|sv)\s*$", resolved.strip())
        if bare_glob and "$(" not in resolved:
            dir_path = bare_glob.group(1)
            result.warnings.append(
                Warning(
                    line_number=line_num,
                    message="bare glob without $(wildcard): use $(sort $(wildcard ...))",
                    category="deprecated",
                )
            )
            label = self._dir_to_verilog_label(dir_path)
            return [label]

        # Handle $(sort $(filter-out ...)) pattern — map the wildcard part
        filter_out_match = re.match(
            r"^\$\(sort\s+\$\(filter-out\s+.+?,\s*\$\(wildcard\s+(.+?)/\*\.(v|sv)\s*\)\s*\)\s*\)$",
            resolved.strip(),
        )
        if filter_out_match:
            dir_path = filter_out_match.group(1)
            label = self._dir_to_verilog_label(dir_path)
            return [label]

        # Handle multi-glob with sort (e.g., cva6 with many $(sort $(wildcard ...)) joined)
        # Tokenize preserving $(...) expressions as single units
        tokens = self._tokenize_make_expr(resolved)
        multi_sort = False
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            swm = re.match(
                r"^\$\(sort\s+\$\(wildcard\s+(.+?)/\*\.(v|sv|svh)\s*\)\s*\)$", token
            )
            if swm:
                dir_path = swm.group(1)
                labels.append(self._dir_to_verilog_label(dir_path))
                multi_sort = True
                continue
            wm = re.match(r"^\$\(wildcard\s+(.+?)/\*\.(v|sv|svh)\s*\)$", token)
            if wm:
                dir_path = wm.group(1)
                labels.append(self._dir_to_verilog_label(dir_path))
                multi_sort = True
                continue
            # Bare glob pattern: path/*.v → :verilog label
            bare_glob = re.match(r"^(.+)/\*\.(v|sv|svh)$", token.strip())
            if bare_glob:
                labels.append(self._dir_to_verilog_label(bare_glob.group(1)))
                continue
            # Single file reference
            label = self._file_to_label(token, result, line_num)
            if label:
                labels.append(label)

        if labels:
            return labels

        # Fallback: try to map as a single file or unresolved
        label = self._file_to_label(resolved.strip(), result, line_num)
        if label:
            return [label]

        return [resolved]  # Return raw if can't resolve

    @staticmethod
    def _tokenize_make_expr(value):
        """Split a Make expression into tokens, preserving $(...) as single units.

        Regular whitespace splitting breaks expressions like
        $(sort $(wildcard path/*.sv)) into fragments. This tokenizer
        tracks parenthesis nesting depth so $(...) groups stay intact.
        """
        tokens = []
        current = []
        depth = 0
        i = 0
        while i < len(value):
            ch = value[i]
            if ch == "$" and i + 1 < len(value) and value[i + 1] == "(":
                current.append("$(")
                depth += 1
                i += 2
                continue
            if ch == "(" and depth > 0:
                current.append(ch)
                depth += 1
            elif ch == ")" and depth > 0:
                current.append(ch)
                depth -= 1
            elif ch in (" ", "\t") and depth == 0:
                if current:
                    tokens.append("".join(current))
                    current = []
            else:
                current.append(ch)
            i += 1
        if current:
            tokens.append("".join(current))
        return tokens

    def _dir_to_verilog_label(self, dir_path):
        """Convert a directory path to a //flow/designs/src/<name>:verilog label."""
        # Normalize path
        dir_path = dir_path.strip().rstrip("/")

        # Check if it's under designs/src/
        src_match = re.search(r"(?:flow/)?designs/src/(.+)$", dir_path)
        if src_match:
            rel_path = src_match.group(1)
            return f"//flow/designs/src/{rel_path}:verilog"

        # Check if it's under flow/platforms/ (deprecated)
        plat_match = re.search(r"(?:flow/)?platforms/([^/]+)(/.*)?$", dir_path)
        if plat_match:
            return f"//flow/platforms/{plat_match.group(1)}{plat_match.group(2) or ''}:verilog"

        return f"//{dir_path}:verilog"

    def _file_to_label(self, path, result, line_num):
        """Convert a file path to a Bazel label."""
        if not path or path.startswith("$("):
            return path  # Can't resolve
        return self._path_to_label(path.strip(), result, line_num)

    def _map_source_file(self, var_name, resolved, ctx, result, line_num):
        """Map a source file variable to Bazel labels.

        Always produces absolute labels (//pkg:file) so they work
        from external repos like @orfs_designs.
        """
        if not resolved:
            return []

        # Unwrap $(sort $(wildcard ...)) and $(wildcard ...) before splitting,
        # since these contain spaces that aren't token separators.
        unwrapped = re.sub(
            r"\$\(sort\s+\$\(wildcard\s+(.+?)\)\s*\)",
            r"\1",
            resolved,
        )
        unwrapped = re.sub(
            r"\$\(wildcard\s+(.+?)\)",
            r"\1",
            unwrapped,
        )

        labels = []

        # Split on whitespace for multi-file variables
        tokens = unwrapped.split()
        for token in tokens:
            token = token.strip()
            if not token:
                continue

            # Map wildcard patterns to filegroup labels.
            # e.g. flow/designs/asap7/swerv_wrapper/lef/*.lef
            #   -> //flow/designs/asap7/swerv_wrapper/lef:lef
            # The target BUILD.bazel must define a matching filegroup.
            if "*" in token or "?" in token:
                dir_part = os.path.dirname(token)
                ext = os.path.splitext(token)[1].lstrip(".")
                # Map file extension to filegroup name
                ext_to_group = {
                    "v": "verilog",
                    "sv": "verilog",
                    "lef": "lef",
                    "lib": "lib",
                    "gz": "gds",
                }
                group_name = ext_to_group.get(ext, ext)
                label = self._path_to_label(
                    dir_part + "/" + group_name, result, line_num
                )
                if label:
                    labels.append(label)
                continue

            label = self._path_to_label(token, result, line_num)
            if label:
                labels.append(label)

        return labels

    def _path_to_label(self, path, result, line_num):
        """Convert a resolved file path to a proper //pkg:file Bazel label."""
        if not path:
            return path

        # Normalize leading "./" — block.mk-style relative paths
        # (e.g. ./designs/asap7/aes/constraint.sdc). Without this they
        # become malformed labels like //./designs/asap7/aes:foo.
        while path.startswith("./"):
            path = path[2:]

        # Already a label
        if path.startswith("//") or path.startswith("@"):
            return path

        # Unresolved variable refs — pass through
        if "$(" in path or "${" in path:
            return path

        # Normalize: ensure path starts with flow/
        if not path.startswith("flow/"):
            if path.startswith(f"{self.designs_home}/"):
                path = f"flow/{path}"
            elif path.startswith(f"{self.flow_home}/"):
                pass  # already has flow/ prefix conceptually
            else:
                # Relative path without flow/ prefix
                if result:
                    result.warnings.append(
                        Warning(
                            line_number=line_num,
                            message="relative path without $(DESIGN_HOME): "
                            "use $(DESIGN_HOME) prefix",
                            category="deprecated",
                        )
                    )
                if path.startswith("designs/"):
                    path = f"flow/{path}"

        # Platform files live under the //flow package (no sub-packages)
        if path.startswith("flow/platforms/"):
            rel = path[
                len("flow/") :
            ]  # e.g. platforms/asap7/verilog/fakeram7_64x256.sv
            return f"//flow:{rel}"

        # Split into package and file: //dir:filename
        if "/" in path:
            dir_part = os.path.dirname(path)
            file_part = os.path.basename(path)
            return f"//{dir_part}:{file_part}"

        return path

    def _resolve_include_path(self, include_path, base_dir):
        """Resolve an include directive path."""
        # Try relative to base_dir first
        candidate = os.path.join(base_dir, include_path)
        if os.path.exists(candidate):
            return candidate

        # Try relative to CWD (for paths like "designs/asap7/riscv32i/config.mk")
        if os.path.exists(include_path):
            return include_path

        # Try relative to flow/
        flow_candidate = os.path.join("flow", include_path)
        if os.path.exists(flow_candidate):
            return flow_candidate

        # Try relative to the flow/ directory derived from base_dir
        # (handles repo rule context where CWD != repo root)
        # base_dir is like .../flow/designs/<platform>/<design>
        # include_path is like designs/src/mock-alu/defaults.mk
        try:
            designs_idx = base_dir.rindex("/designs/")
            flow_dir = base_dir[:designs_idx]
            flow_rel = os.path.join(flow_dir, include_path)
            if os.path.exists(flow_rel):
                return flow_rel
        except ValueError:
            pass

        return None

    def _warn_conditional(self, line, line_num, result):
        """Add a warning for conditional blocks."""
        if "FLOW_VARIANT" in line:
            result.warnings.append(
                Warning(
                    line_number=line_num,
                    message="ifeq FLOW_VARIANT: split into separate config.mk per variant",
                    category="deprecated",
                )
            )
        elif "USE_FILL" in line:
            result.warnings.append(
                Warning(
                    line_number=line_num,
                    message="ifeq USE_FILL: set DESIGN_TYPE unconditionally",
                    category="deprecated",
                )
            )
        elif "BLOCKS" in line:
            result.warnings.append(
                Warning(
                    line_number=line_num,
                    message="ifeq BLOCKS: use separate config for with/without blocks",
                    category="deprecated",
                )
            )
        elif "SYNTH_MOCK_LARGE_MEMORIES" in line:
            result.warnings.append(
                Warning(
                    line_number=line_num,
                    message="ifeq SYNTH_MOCK_LARGE_MEMORIES: simplify to unconditional",
                    category="deprecated",
                )
            )
        else:
            # Generic conditional warning
            cond_var = re.search(r"\$\((\w+)\)", line)
            var_name = cond_var.group(1) if cond_var else "unknown"
            result.warnings.append(
                Warning(
                    line_number=line_num,
                    message=f"ifeq {var_name}: consider simplifying or removing conditional",
                    category="deprecated",
                )
            )


def generate_orfs_flow(parsed, module_name="orfs"):
    """Generate an orfs_flow() Bazel target string from a ParsedDesign.

    Args:
        parsed: ParsedDesign instance.
        module_name: Module name for cross-repo labels (e.g., "orfs").

    Returns:
        String containing the orfs_flow() Bazel call.
    """
    lines = []
    lines.append('load("@bazel-orfs//:openroad.bzl", "orfs_flow")')
    lines.append("")

    # Generate sub-macro targets first
    for block_config in parsed.block_configs:
        lines.append(f"# Sub-macro: {block_config.design_name}")
        lines.append(
            _format_orfs_flow_call(block_config, module_name, abstract_stage="cts")
        )
        lines.append("")

    # Generate main target
    if parsed.warnings:
        has_deprecated = any(
            w.category == "deprecated"
            for w in parsed.warnings
            if isinstance(w, Warning)
        )
        if has_deprecated:
            lines.append(
                "# NOTE: This config uses deprecated features. Run the linter for details."
            )
    lines.append(f"# Auto-generated from {os.path.basename(parsed.config_path)}")
    lines.append(_format_orfs_flow_call(parsed, module_name))
    return "\n".join(lines) + "\n"


def _format_orfs_flow_call(parsed, module_name, abstract_stage=None):
    """Format a single orfs_flow() call."""
    parts = []

    # name
    name = parsed.design_name or parsed.design_nickname
    parts.append(f'    name = "{name}",')

    # top (only if different from name)
    if parsed.design_name and parsed.design_name != name:
        parts.append(f'    top = "{parsed.design_name}",')

    # abstract_stage (for sub-macros)
    if abstract_stage:
        parts.append(f'    abstract_stage = "{abstract_stage}",')

    # verilog_files
    if parsed.verilog_files:
        if len(parsed.verilog_files) == 1:
            vf = parsed.verilog_files[0]
            # Add module prefix for cross-repo refs
            if vf.startswith("//"):
                vf = f"@{module_name}{vf}"
            parts.append(f'    verilog_files = ["{vf}"],')
        else:
            parts.append("    verilog_files = [")
            for vf in parsed.verilog_files:
                if vf.startswith("//"):
                    vf = f"@{module_name}{vf}"
                parts.append(f'        "{vf}",')
            parts.append("    ],")

    # pdk
    pdk_label = f"@{module_name}//flow:{parsed.platform}"
    parts.append(f'    pdk = "{pdk_label}",')

    # macros (from BLOCKS)
    if parsed.block_configs:
        macro_refs = []
        for bc in parsed.block_configs:
            bn = bc.design_name or bc.design_nickname
            macro_refs.append(f'        ":{bn}_generate_abstract",')
        parts.append("    macros = [")
        parts.extend(macro_refs)
        parts.append("    ],")

    # arguments
    if parsed.arguments:
        parts.append("    arguments = {")
        for key in sorted(parsed.arguments.keys()):
            val = parsed.arguments[key]
            parts.append(f'        "{key}": "{val}",')
        parts.append("    },")

    # sources
    if parsed.sources:
        parts.append("    sources = {")
        for key in sorted(parsed.sources.keys()):
            vals = parsed.sources[key]
            formatted_vals = []
            for v in vals:
                if v.startswith("//"):
                    v = f"@{module_name}{v}"
                formatted_vals.append(f'"{v}"')
            parts.append(f'        "{key}": [{", ".join(formatted_vals)}],')
        parts.append("    },")

    return "orfs_flow(\n" + "\n".join(parts) + "\n)"


def lint_report(parsed):
    """Generate a human-readable lint report for a ParsedDesign."""
    lines = []
    for w in parsed.warnings:
        if isinstance(w, Warning):
            prefix = {
                "deprecated": "WARNING",
                "unsupported": "ERROR",
                "info": "INFO",
                "error": "ERROR",
            }.get(w.category, "WARNING")
            lines.append(f"{parsed.config_path}:{w.line_number}: {prefix}: {w.message}")
        else:
            lines.append(str(w))
    return "\n".join(lines)


def discover_configs(designs_dir, platforms=None):
    """Discover all config.mk files under a designs directory.

    Args:
        designs_dir: Path to the designs directory.
        platforms: Optional list of platforms to include. If None, all platforms.

    Returns:
        List of config.mk file paths.
    """
    configs = []
    designs_path = Path(designs_dir)
    if not designs_path.exists():
        return configs

    for platform_dir in sorted(designs_path.iterdir()):
        if not platform_dir.is_dir():
            continue
        if platform_dir.name == "src":
            continue
        if platforms and platform_dir.name not in platforms:
            continue
        for design_dir in sorted(platform_dir.iterdir()):
            if not design_dir.is_dir():
                continue
            config_mk = design_dir / "config.mk"
            if config_mk.exists():
                configs.append(str(config_mk))
    return configs


def main():
    parser = argparse.ArgumentParser(
        description="Parse ORFS config.mk design DSL files"
    )
    parser.add_argument("configs", nargs="*", help="config.mk files to parse")
    parser.add_argument(
        "--all",
        metavar="DESIGNS_DIR",
        help="Discover and parse all config.mk files under DESIGNS_DIR",
    )
    parser.add_argument(
        "--platforms", help="Comma-separated list of platforms to include"
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="Print lint warnings instead of parsed output",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--generate", action="store_true", help="Generate orfs_flow() Bazel targets"
    )
    parser.add_argument(
        "--module-name", default="orfs", help="Module name for cross-repo labels"
    )

    args = parser.parse_args()

    configs = list(args.configs)
    if args.all:
        platforms = args.platforms.split(",") if args.platforms else None
        configs.extend(discover_configs(args.all, platforms))

    if not configs:
        parser.print_help()
        sys.exit(1)

    mk_parser = ConfigMkParser()
    results = []
    exit_code = 0

    for config_path in configs:
        parsed = mk_parser.parse(config_path)
        results.append(parsed)

        if args.lint:
            report = lint_report(parsed)
            if report:
                print(report)
                exit_code = 1
        elif args.generate:
            print(generate_orfs_flow(parsed, args.module_name))
        elif args.json:
            pass  # Batch output below
        else:
            # Default: print summary
            print(f"{config_path}:")
            print(f"  platform: {parsed.platform}")
            print(f"  design_name: {parsed.design_name}")
            print(f"  design_nickname: {parsed.design_nickname}")
            print(f"  verilog_files: {parsed.verilog_files}")
            print(f"  sources: {parsed.sources}")
            print(f"  arguments: {parsed.arguments}")
            print(f"  blocks: {parsed.blocks}")
            print(f"  has_conditionals: {parsed.has_conditionals}")
            if parsed.warnings:
                print(f"  warnings: {len(parsed.warnings)}")
            print()

    if args.json:
        output = [r.to_dict() for r in results]
        print(json.dumps(output, indent=2))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
