"""Only Wait for the Real Work: what is shown and what is said.

A scene is (kind, options, sentences). The kind picks its picture in
video.py; each sentence is spoken and burned in as one caption, and the
scene lasts as long as its sentences. "animate" draws a scene over its
first second; "gauge" sets the corner gauge, minutes until you can decide
per lane, which slides from the scene before.

Every number is measured on asap7 riscv32i on one 16-core machine, each
run once, or comes from earlier runs and says so:

  bazelisk build, synthesis to final, cold         359 s
  bazelisk build, a placement change, to grt       191 s
  bazelisk build, switching back                     2 s
  dirty lane, place + cts + grt by hand             106 s
  dirty lane, the global placement substep           12 s
  team cache, fresh output base, nothing run        234 s

FULL is the talk, landscape; SHORT the cell-phone cut.
"""

TITLE = "Only Wait for the Real Work"

# Written form -> spoken form, for the narrator.
SAY = [
    ("bazelisk", "bazel-isk"),
    ("global_place.tcl", "global place dot tickle"),
    ("riscv32i", "risk five thirty-two I"),
    ("OpenROAD", "Open Road"),
    ("ORFS", "orfs"),
    ("XiangShan", "Shyang-shan"),
    ("WNS", "worst negative slack"),
    ("VPN", "V P N"),
    ("AI", "A I"),
    ("CI", "C I"),
]


def say(text):
    for written, spoken in SAY:
        text = text.replace(written, spoken)
    return text


STAGES = [
    ("floorplan", 28),
    ("place", 26),
    ("cts", 31),
    ("grt", 49),
    ("route", 214),
    ("final", 13),
]

MAKE = [
    "$ make clean_cts",
    "$ make",
    "  floorplan: up to date",
    "  place: up to date",
    "  cts, grt, route, final: run again",
]

GUI = [
    "$ bazelisk run //my:design_final gui_final",
    "odb-debug: open the GUI: http://10.7.0.3:41213/?token=...",
]
VPN = "10.7.0.3: your VPN address (made up for this video)"

EVERYTHING = [("make", 6.0), ("Bazel", 6.0)]
AT_GRT = [("make", 1.8), ("Bazel", 3.2)]
SWITCH_BACK = [("make", 1.8), ("Bazel", 0.0)]
SCRIPT_EDIT = [("make", 0.2), ("Bazel", 6.0)]

FULL = [
    (
        "landscape",
        {"animate": True, "walk": [0.15, 0.7, 0.97]},
        [
            "Physical design is a landscape of hills and cliffs. Early on, the problems are big, and any rough estimate tells you which way is down.",
            "Near the end you are choosing between candidates a few percent apart, and you stop when the worst slack reaches zero.",
            "A few picoseconds then look like a big percentage. Part of that is the illusion of a small number; part is real, because a few more things have to go right to get across.",
        ],
    ),
    (
        "timeline",
        {"animate": True, "grow": True, "gauge": {1: EVERYTHING}},
        [
            "Only one build does not need to be fast: the last one before tapeout. Every build before it exists to give you data for a decision, and the space of decisions is vast.",
            "While you wait, you switch to something else, drift into speculative work and lose focus. That is true of people and of AI agents. So let's count minutes until you can decide.",
        ],
    ),
    (
        "stagebars",
        {
            "bars": STAGES,
            "animate": True,
            "grow": True,
            "cut": [None, "grt", "grt"],
            "gauge": {1: AT_GRT},
        },
        [
            "Here is a small RISC-V core, riscv32i, on this machine: six minutes from floorplan to final, and detailed route is most of it.",
            "By global route you have placement, the clock tree, and a routed estimate of wiring and timing: nearly everything you need to decide.",
            "For thirty years, academia, industry and startups have tried to predict routing without routing. None of the predictions replaced running it. So run global route, and stop there.",
        ],
    ),
    (
        "terminal",
        {"lines": MAKE, "show": [5]},
        [
            "ORFS with make already reruns from a stage. Keep that. What follows adds to it."
        ],
    ),
    (
        "buildrun",
        {"animate": True, "light": [0, 1, 2]},
        [
            "bazelisk is the one thing you install. bazelisk build runs each stage sealed off from your machine, and remembers each result by everything that went into it.",
            "bazelisk run builds, then runs the result in your own environment: your terminal, your browser.",
            "We use both.",
        ],
    ),
    (
        "cards",
        {
            "animate": True,
            "cards": [
                ("density 0.10", "kept"),
                ("density 0.14", "191 s to grt"),
                ("a colleague's", "from the team cache"),
            ],
            "select": [1, 0, 2],
            "gauge": {0: AT_GRT, 1: SWITCH_BACK},
        },
        [
            "Change a placement setting and stop at global route: about three minutes with Bazel, under two by hand with make. On a design this small, Bazel's bookkeeping costs time.",
            "Now switch back to the old setting. Bazel still has it: two seconds. With make you would run it again.",
            "And a result someone else built, a colleague or CI, arrives from your team's cache as a download. On XiangShan, six hours cold becomes minutes.",
        ],
    ),
    (
        "deps",
        {"animate": True, "gauge": {1: SCRIPT_EDIT}},
        [
            "Bazel's dependencies are kept simple on purpose. Edit global_place.tcl, and Bazel reruns every stage that reads the flow scripts.",
            "In the dirty lane, plain ORFS with make, you rerun global placement alone: twelve seconds. Where precision pays, the dependencies are made finer; elsewhere, the dirty lane covers it.",
        ],
    ),
    (
        "terminal",
        {"lines": GUI, "show": [2], "note": VPN, "gauge": "hide"},
        [
            "To look at a result, bazelisk run loads it once and keeps it loaded: one click from your laptop, over your VPN."
        ],
    ),
    (
        "image",
        {
            "image": "gui",
            "label": "a routed design in OpenROAD's GUI, in a browser",
            "gauge": "hide",
        },
        ["One click, and the design is there, already loaded."],
    ),
    (
        "repair",
        {"animate": True, "gauge": "hide"},
        [
            "What is left is real work, and the biggest part of it is repair: on riscv32i, sixty-two percent of the stage it runs in.",
            "You only know repair is done when there is nothing left to repair, and its history does not predict what comes next. There is no oracle.",
            "How long to run it is a policy decision. The faster the rest of the loop, the more of those decisions you can test.",
        ],
    ),
    (
        "title",
        {"sub": "bazelisk build, then bazelisk run to look", "gauge": "hide"},
        ["Only wait for the real work."],
    ),
]

SHORT = [
    (
        "timeline",
        {"animate": True, "grow": True, "gauge": {0: EVERYTHING}},
        [
            "Only the last build before tapeout may be slow. Every build before it is data for a decision."
        ],
    ),
    (
        "stagebars",
        {
            "bars": STAGES,
            "animate": True,
            "grow": True,
            "cut": ["grt"],
            "gauge": {0: AT_GRT},
        },
        [
            "By global route you have nearly everything you need to decide. Stop there: two minutes instead of six."
        ],
    ),
    (
        "cards",
        {
            "animate": True,
            "cards": [("density 0.10", "kept"), ("density 0.14", "191 s to grt")],
            "select": [0],
            "gauge": {0: SWITCH_BACK},
        },
        [
            "Switch back to an earlier setting, and Bazel still has the result: two seconds."
        ],
    ),
    (
        "repair",
        {"animate": True, "gauge": "hide"},
        [
            "The rest is real work, mostly repair, and when to stop it is a policy with no oracle."
        ],
    ),
    (
        "title",
        {"sub": "bazelisk build, then bazelisk run to look", "gauge": "hide"},
        ["Only wait for the real work."],
    ),
]

SCRIPTS = {"full": FULL, "short": SHORT}
