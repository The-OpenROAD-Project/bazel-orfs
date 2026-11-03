# OpenROAD #11859: "Expand clock" in the timing widget. A path's clock
# network is one row until the box is ticked; the base viewer has no box
# and lists every clock pin.
import os
import runpy

_here = os.path.dirname(__file__)

STEPS = runpy.run_path(os.path.join(_here, "timing_setup.py"))["SETUP"] + [
    {"frame": 600},
    {"click": ".timing-path-table-container tr >> nth=1", "steps": 14},
    {"wait": 1500},
    {"frame": 2500},
    {"click": ".timing-expand-clock input", "optional": True, "steps": 14},
    {"wait": 1000},
    {"frame": 2500},
    {"click": ".timing-expand-clock input", "optional": True, "steps": 2},
    {"wait": 1000},
    {"frame": 2000},
]
VIEWPORT = "1600x900"
CLIP = ".ide-pane-right"
WIDTH = 800
