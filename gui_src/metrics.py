"""ORFS-aware file reader for build artifacts, metrics, logs, and reports.

Mirrors stage metadata from private/stages.bzl to locate files in bazel-bin/.
Understands all ORFS JSON metric fields.
"""

import json
import os
import time
from pathlib import Path

# Mirrors STAGE_SUBSTEPS from private/stages.bzl
STAGE_SUBSTEPS = {
    "synth": ["1_1_yosys_canonicalize", "1_2_yosys"],
    "floorplan": [
        "2_1_floorplan",
        "2_2_floorplan_macro",
        "2_3_floorplan_tapcell",
        "2_4_floorplan_pdn",
    ],
    "place": [
        "3_1_place_gp_skip_io",
        "3_2_place_iop",
        "3_3_place_gp",
        "3_4_place_resized",
        "3_5_place_dp",
    ],
    "cts": ["4_1_cts"],
    "grt": ["5_1_grt"],
    "route": ["5_2_route", "5_3_fillcell"],
    "final": ["6_1_merge", "6_report"],
}

# Stage output files (the primary result)
STAGE_OUTPUTS = {
    "synth": "1_synth.odb",
    "floorplan": "2_floorplan.odb",
    "place": "3_place.odb",
    "cts": "4_cts.odb",
    "grt": "5_1_grt.odb",
    "route": "5_route.odb",
    "final": "6_final.odb",
}

# Report files per stage
STAGE_REPORTS = {
    "floorplan": ["2_floorplan_final.rpt"],
    "cts": ["4_cts_final.rpt"],
    "grt": ["5_global_route.rpt", "congestion.rpt"],
    "route": ["5_route_drc.rpt"],
    "final": ["6_finish.rpt", "VDD.rpt", "VSS.rpt"],
}

# JSON metric files per stage
STAGE_JSONS = {
    "floorplan": ["2_1_floorplan.json", "2_2_floorplan_macro.json",
                  "2_3_floorplan_tapcell.json", "2_4_floorplan_pdn.json"],
    "place": ["3_1_place_gp_skip_io.json", "3_2_place_iop.json",
              "3_3_place_gp.json", "3_4_place_resized.json", "3_5_place_dp.json"],
    "cts": ["4_1_cts.json"],
    "grt": ["5_1_grt.json"],
    "route": ["5_2_route.json", "5_3_fillcell.json"],
    "final": ["6_report.json", "6_1_fill.json"],
}

# Key PPA metric fields extracted from ORFS JSON
PPA_FIELDS = {
    "power": "finish__power__total",
    "area": "finish__design__instance__area",
    "worst_slack": "finish__timing__setup__ws",
    "fmax": "finish__timing__fmax",
    "instances": "finish__design__instance__count",
    "utilization": "finish__design__instance__utilization",
    "die_area": "finish__design__die__area",
    "wirelength": "finish__route__wirelength",
}


class MetricsReader:
    def __init__(self, bazel_bin):
        self.bazel_bin = Path(bazel_bin)
        self._file_mtimes = {}
        self._status_cache = None
        self._status_cache_time = 0
        self._status_cache_ttl = 3  # seconds

    def _find_design_dir(self, design_path):
        """Find the design directory in bazel-bin.

        design_path is like 'pkg/design' or just 'design'.
        Files are at bazel-bin/<design_path>/logs/, etc.
        """
        return self.bazel_bin / design_path

    def get_metrics(self, design_path):
        """Read all JSON metrics for a design, across all stages."""
        base = self._find_design_dir(design_path)
        logs_dir = base / "logs"
        result = {"stages": {}, "ppa": {}}

        for stage, json_files in STAGE_JSONS.items():
            stage_metrics = {}
            for jf in json_files:
                json_path = logs_dir / jf
                if json_path.exists():
                    try:
                        data = json.loads(json_path.read_text())
                        stage_metrics[jf] = data
                    except json.JSONDecodeError:
                        stage_metrics[jf] = {"error": "invalid JSON"}
            if stage_metrics:
                result["stages"][stage] = stage_metrics

        # Extract PPA summary from final stage metrics
        final_json = logs_dir / "6_report.json"
        if final_json.exists():
            try:
                data = json.loads(final_json.read_text())
                for key, field in PPA_FIELDS.items():
                    # Handle fmax which has clock name suffix
                    if field == "finish__timing__fmax":
                        for k, v in data.items():
                            if k.startswith(field):
                                result["ppa"][key] = v
                                break
                    elif field in data:
                        result["ppa"][field.split("__")[-1]] = data[field]
                        result["ppa"][key] = data[field]
            except json.JSONDecodeError:
                pass

        return result

    def get_log(self, design_path, stage):
        """Read log file for a specific stage/substep."""
        base = self._find_design_dir(design_path)
        logs_dir = base / "logs"

        # Try exact substep name first
        log_path = logs_dir / f"{stage}.log"
        if log_path.exists():
            return log_path.read_text()

        # Try stage substeps
        substeps = STAGE_SUBSTEPS.get(stage, [])
        parts = []
        for sub in substeps:
            sub_path = logs_dir / f"{sub}.log"
            if sub_path.exists():
                parts.append(f"=== {sub} ===\n{sub_path.read_text()}")
        if parts:
            return "\n\n".join(parts)

        raise FileNotFoundError(f"No log found for {design_path}/{stage}")

    def get_report(self, design_path, stage):
        """Read report file(s) for a stage."""
        base = self._find_design_dir(design_path)
        reports_dir = base / "reports"

        report_names = STAGE_REPORTS.get(stage, [])
        parts = []
        for name in report_names:
            rpt_path = reports_dir / name
            if rpt_path.exists():
                parts.append(f"=== {name} ===\n{rpt_path.read_text()}")

        if parts:
            return "\n\n".join(parts)

        # Try generic report name
        rpt_path = reports_dir / f"{stage}.rpt"
        if rpt_path.exists():
            return rpt_path.read_text()

        raise FileNotFoundError(f"No report found for {design_path}/{stage}")

    def get_stage_status(self, design_path, stage):
        """Check build status for a stage: 'done', 'stale', or 'missing'."""
        base = self._find_design_dir(design_path)
        output_file = STAGE_OUTPUTS.get(stage)
        if not output_file:
            return "unknown"

        results_dir = base / "results"
        output_path = results_dir / output_file
        if not output_path.exists():
            # Also check directly under base
            output_path = base / output_file
            if not output_path.exists():
                return "missing"

        return "done"

    def _scan_output_files(self):
        """Single walk of bazel-bin to find all stage output files.

        Returns dict of {filepath_str: (rel_path, stage, mtime)}.
        Much faster than 7 separate rglob calls.
        """
        # Build reverse lookup: filename -> stage
        filename_to_stage = {f: s for s, f in STAGE_OUTPUTS.items()}
        results = {}
        if not self.bazel_bin.exists():
            return results
        bin_str = str(self.bazel_bin)
        for dirpath, _dirnames, filenames in os.walk(bin_str):
            for fname in filenames:
                stage = filename_to_stage.get(fname)
                if stage:
                    full = os.path.join(dirpath, fname)
                    rel = os.path.relpath(full, bin_str)
                    try:
                        mtime = os.path.getmtime(full)
                    except OSError:
                        mtime = 0
                    results[full] = (rel, stage, mtime)
        return results

    def get_all_status(self):
        """Scan bazel-bin for all designs and their stage statuses. Cached for 3s."""
        now = time.time()
        if self._status_cache is not None and now - self._status_cache_time < self._status_cache_ttl:
            return self._status_cache
        result = {}
        for _full, (rel, stage, _mtime) in self._scan_output_files().items():
            design_path = str(Path(rel).parent)
            if design_path not in result:
                result[design_path] = {}
            result[design_path][stage] = "done"
        self._status_cache = result
        self._status_cache_time = now
        return result

    def check_changes(self, since):
        """Check for files modified since timestamp. Returns list of changed paths."""
        changes = []
        for full, (rel, stage, mtime) in self._scan_output_files().items():
            prev = self._file_mtimes.get(full, 0)
            if mtime > since or mtime > prev:
                self._file_mtimes[full] = mtime
                if mtime > prev:
                    changes.append({"path": rel, "stage": stage, "time": mtime})
        return changes
