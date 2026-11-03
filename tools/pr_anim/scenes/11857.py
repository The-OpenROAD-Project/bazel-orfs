# OpenROAD #11857: the slack histogram's axis title names its clocks.
# The pointer goes to the axis title under the histogram.
import os
import runpy

SETUP = runpy.run_path(os.path.join(os.path.dirname(__file__), "charts_setup.py"))[
    "SETUP"
]
STEPS = SETUP + [
    {"frame": 800},
    {"move": ".charts-canvas", "anchor": "bottom", "dx": 140, "dy": -20, "steps": 16},
    {"frame": 3000},
]
VIEWPORT = "1600x900"
CLIP = ".ide-pane-right"
WIDTH = 800
