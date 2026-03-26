"""Bazel query wrapper with caching and DOT→Cytoscape JSON parsing.

Discovers ORFS targets via gui_manifest JSON files emitted by orfs_flow(),
parses dependency graphs, and decomposes target names into
design/variant/stage components.
"""

import json
import re
import subprocess
import time
from pathlib import Path

ALL_STAGES = [
    "synth",
    "floorplan",
    "place",
    "cts",
    "grt",
    "route",
    "final",
    "generate_abstract",
    "generate_metadata",
    "test",
    "update_rules",
]

# Stages that appear in typical user-facing targets
USER_STAGES = ["synth", "floorplan", "place", "cts", "grt", "route", "final"]

STAGE_COLORS = {
    "synth": "#6366f1",
    "floorplan": "#8b5cf6",
    "place": "#14b8a6",
    "cts": "#f59e0b",
    "grt": "#f97316",
    "route": "#ef4444",
    "final": "#22c55e",
    "generate_abstract": "#64748b",
    "generate_metadata": "#64748b",
    "test": "#64748b",
    "update_rules": "#64748b",
}


class QueryRunner:
    def __init__(self, workspace, cache_ttl=30):
        self.workspace = workspace
        self.bazel_bin = Path(workspace) / "bazel-bin"
        self.cache_ttl = cache_ttl
        self._cache = {}

    def _run_query(self, query_args):
        cache_key = tuple(query_args)
        now = time.time()
        if cache_key in self._cache:
            result, timestamp = self._cache[cache_key]
            if now - timestamp < self.cache_ttl:
                return result

        cmd = ["bazelisk", "query"] + list(query_args)
        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout
            self._cache[cache_key] = (output, now)
            return output
        except subprocess.TimeoutExpired:
            raise RuntimeError("bazel query timed out after 60s")
        except FileNotFoundError:
            raise RuntimeError("bazelisk not found on PATH")

    def get_targets(self):
        """Discover ORFS flows via gui_manifest JSON files (DRY — single source of truth).

        Falls back to bazel query target name parsing if no manifests found.
        """
        designs = {}

        # Primary: read gui_manifest files from bazel-bin
        manifests = list(self.bazel_bin.rglob("*_gui_manifest"))
        for manifest_path in manifests:
            try:
                meta = json.loads(manifest_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            pkg = str(manifest_path.parent.relative_to(self.bazel_bin))
            name = meta.get("name", "")
            variant = meta.get("variant", "")
            stages = meta.get("stages", [])
            is_macro = meta.get("is_macro", False)

            key = f"{pkg}/{name}" + (f"_{variant}" if variant else "")
            designs[key] = {
                "package": pkg,
                "design": name,
                "variant": variant,
                "top": meta.get("top", name),
                "is_macro": is_macro,
                "abstract_stage": meta.get("abstract_stage", ""),
                "macros": meta.get("macros", []),
                "variants": {
                    variant or "default": {
                        "stages": {
                            stage: f"//{pkg}:{name}{'_' + variant if variant else ''}_{stage}"
                            for stage in stages
                        },
                    },
                },
            }

        # Fallback: query if no manifests found
        if not designs:
            designs = self._get_targets_from_query()

        all_targets = []
        for d in designs.values():
            for v in d.get("variants", {}).values():
                all_targets.extend(v.get("stages", {}).values())

        return {"designs": designs, "targets": all_targets}

    def _get_targets_from_query(self):
        """Fallback: discover targets via bazel query and parse names."""
        output = self._run_query(
            ['kind("orfs_.*", //...)', "--output=label"]
        )
        targets = [line.strip() for line in output.splitlines() if line.strip()]

        designs = {}
        for target in targets:
            parsed = parse_target(target)
            if parsed is None:
                continue
            pkg, design, variant, stage = parsed
            key = f"{pkg}/{design}"
            if key not in designs:
                designs[key] = {
                    "package": pkg,
                    "design": design,
                    "variants": {},
                }
            var_key = variant or "default"
            if var_key not in designs[key]["variants"]:
                designs[key]["variants"][var_key] = {"stages": {}}
            designs[key]["variants"][var_key]["stages"][stage] = target

        return designs

    def get_graph(self, target="//..."):
        """Get dependency graph as Cytoscape.js JSON."""
        output = self._run_query(
            [f"deps({target})", "--output=graph", "--noimplicit_deps"]
        )
        return parse_dot_to_cytoscape(output)

    def invalidate_cache(self):
        self._cache.clear()


def parse_target(label):
    """Parse a bazel label into (package, design, variant, stage).

    ORFS targets follow: //<pkg>:<design>[_<variant>]_<stage>
    Returns None if the label doesn't match an ORFS stage target.
    """
    match = re.match(r"//([^:]*):(.+)", label)
    if not match:
        return None

    pkg = match.group(1)
    name = match.group(2)

    # Try each stage suffix, longest first to avoid ambiguity
    for stage in sorted(ALL_STAGES, key=len, reverse=True):
        suffix = f"_{stage}"
        if name.endswith(suffix):
            prefix = name[: -len(suffix)]
            # prefix is either "design" or "design_variant"
            # We can't reliably split design from variant without more context,
            # so we treat the entire prefix as the design name for now.
            # Variants are detected by looking for multiple prefixes per package.
            return (pkg, prefix, None, stage)

    return None


def parse_dot_to_cytoscape(dot_output):
    """Parse Graphviz DOT output from bazel query into Cytoscape.js JSON."""
    nodes = {}
    edges = []

    for line in dot_output.splitlines():
        line = line.strip()

        # Node definition: "//pkg:target" [label="..."]
        node_match = re.match(r'"([^"]+)"\s*(\[.*\])?;?\s*$', line)
        if node_match and "->" not in line:
            label = node_match.group(1)
            if label.startswith("//"):
                parsed = parse_target(label)
                stage = parsed[3] if parsed else None
                color = STAGE_COLORS.get(stage, "#94a3b8")
                nodes[label] = {
                    "data": {
                        "id": label,
                        "label": label.split(":")[-1] if ":" in label else label,
                        "stage": stage,
                        "color": color,
                    }
                }
            continue

        # Edge: "//a:b" -> "//c:d"
        edge_match = re.match(r'"([^"]+)"\s*->\s*"([^"]+)"', line)
        if edge_match:
            source = edge_match.group(1)
            target = edge_match.group(2)
            if source.startswith("//") and target.startswith("//"):
                # Ensure nodes exist
                for n in (source, target):
                    if n not in nodes:
                        parsed = parse_target(n)
                        stage = parsed[3] if parsed else None
                        color = STAGE_COLORS.get(stage, "#94a3b8")
                        nodes[n] = {
                            "data": {
                                "id": n,
                                "label": n.split(":")[-1],
                                "stage": stage,
                                "color": color,
                            }
                        }
                edges.append(
                    {"data": {"source": source, "target": target}}
                )

    return {
        "elements": {
            "nodes": list(nodes.values()),
            "edges": edges,
        }
    }
