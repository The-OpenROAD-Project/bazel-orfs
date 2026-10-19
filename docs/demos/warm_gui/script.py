"""ORFS, at the speed of your ideas: what is shown and what is said.

A short hook for ORFS users: bazel-orfs is ORFS with a memory, and it is
still ORFS. One headline on screen per scene; the spoken sentences go in
the .srt. A scene is (kind, options, sentences); "animate" draws a scene
over its first second, and "headline" is the one thing to read.

Measured on asap7 riscv32i on one 16-core machine, each run once:
switching back to an earlier setting 1.9 s (bazelisk build, to global
route); floorplan to global route 134 s, to final 361 s (ORFS make in a
plain tree). ideas/videos.md has the rest and the conditions.

FULL is the video, SAMPLE one scene to judge the pace before a full
render.
"""

TITLE = "ORFS, at the speed of your ideas"

# Written form -> spoken form, for the narrator.
SAY = [
    ("bazelisk", "bazel-isk"),
    ("bazel-orfs", "bazel orfs"),
    ("OpenROAD", "Open Road"),
    ("ORFS", "orfs"),
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

BY_HAND = [
    "$ cd tmp/orfs/flow/designs/asap7/riscv32i/riscv_top",
    "$ ./make do-3_3_place_gp",
]

MEMORY = (
    "memory",
    {"animate": True, "headline": "ORFS, with a memory"},
    [
        "bazel-orfs runs the ORFS flow you know.",
        "It saves every result, together with the exact inputs that made it.",
        "Run it again with exactly the same inputs, and you get the saved result.",
    ],
)

TALK = [
    (
        "timeline",
        {
            "animate": True,
            "grow": True,
            "answers": True,
            "headline": "Every build answers a question",
        },
        [
            "Every build before tapeout answers a question about your design.",
            "The more questions you can ask in a day, the better your design becomes.",
        ],
    ),
    MEMORY,
    (
        "cards",
        {
            "animate": True,
            "cards": [("a setting you tried", "kept"), ("a new setting", "running")],
            "select": [1, 0],
            "headline": {0: "Go back", 1: "2 seconds"},
        },
        [
            "Go back to a setting you tried before.",
            "The answer is already there, in two seconds.",
        ],
    ),
    (
        "stagebars",
        {
            "bars": STAGES,
            "animate": True,
            "grow": True,
            "cut": ["grt"],
            "headline": "2 minutes, not 6",
        },
        [
            "Most questions are answered by global route. Stop there, and you have it in two minutes."
        ],
    ),
    (
        "terminal",
        {"lines": BY_HAND, "show": [2], "headline": "Still ORFS"},
        ["Want to work by hand? Step into a plain ORFS tree, and use make as always."],
    ),
    (
        "title",
        {"sub": "One install: bazelisk.   github.com/The-OpenROAD-Project/bazel-orfs"},
        ["One install: bazelisk. Then ask as many questions as you like."],
    ),
]

SCRIPTS = {"full": TALK, "sample": [MEMORY]}
