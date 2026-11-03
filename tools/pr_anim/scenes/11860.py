# OpenROAD #11860: a busy cursor while a timing report is built. A click
# on a histogram bin, its request held 2 s (ws_delay: gcd answers in
# milliseconds; say so under the animation).
import os
import runpy

_here = os.path.dirname(__file__)

STEPS = (
    runpy.run_path(os.path.join(_here, "charts_setup.py"))["SETUP"]
    + [
        {"frame": 600},
        {"move": [1060, 700], "steps": 14},
        {"ws_delay": 2000},
        {"click": [1060, 700], "steps": 1},
    ]
    + [{"frame": 200}] * 15
    + [
        {"wait": 1000},
        {"frame": 2000},
    ]
)
VIEWPORT = "1600x900"
CLIP = ".ide-pane-right"
WIDTH = 800
