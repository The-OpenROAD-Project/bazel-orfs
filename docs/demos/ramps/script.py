"""On and off ORFS: what is shown and what is said.

A short video for ORFS users, peers and testers: import an ORFS design
into a bazel-orfs clone, build it, and export it back to make. One
headline on screen per scene; the spoken sentences go in the .srt. A scene
is (kind, options, sentences); "animate" draws a scene over its first
second, and "headline" is the one thing to read.

Measured on asap7 gcd, docs/ramps.md: about three minutes from RTL to
final once OpenROAD and Yosys are built (30 to 60 minutes the first time
in a fresh clone), a rebuild with nothing changed 0.4 s; the export run
with ORFS's make gives a byte-identical 5_route.odb.

FULL is the video, SAMPLE one scene to judge the pace before a full
render.
"""

# How the narrator says ORFS, bazelisk and the rest is
# docs/demos/pronunciation.py, the same for every video.
import pronunciation

TITLE = "On and off ORFS"

IMPORT = [
    "$ git clone .../bazel-orfs && cd bazel-orfs",
    "$ bazelisk run //:import -- \\",
    "    ~/ORFS/flow/designs/asap7/gcd",
    "import: 3 files into imported/asap7/gcd",
]

BUILD = [
    "orfs_flow(",
    '    name = "gcd",',
    '    arguments = {"PLACE_DENSITY": "0.35", ...},',
    '    verilog_files = ["designs/src/gcd/gcd.v"],',
    ")",
]

EXPORT = [
    "$ bazelisk run //:export -- \\",
    "    ~/ORFS/flow/designs/asap7/gcd-bazel \\",
    "    //imported/asap7/gcd:gcd",
    "$ cd ~/ORFS/flow",
    "$ make DESIGN_CONFIG=./designs/asap7/gcd-bazel/config.mk",
]

ON = (
    "terminal",
    {"lines": IMPORT, "show": [4, 4], "headline": "On: import"},
    [
        "Start in a clone of bazel-orfs, and import a design from your ORFS checkout.",
        "Your checkout is only read.",
    ],
)

TALK = [
    (
        "title",
        {"sub": "bazel-orfs helps you with ORFS. It does not replace it."},
        ["bazel-orfs helps you with ORFS. It does not replace it."],
    ),
    ON,
    (
        "terminal",
        {"lines": BUILD, "show": [5, 5], "headline": "One setting per variable"},
        [
            "Import writes a build file, with one setting per config.mk variable.",
            "Ask your AI to make it idiomatic.",
        ],
    ),
    (
        "cards",
        {
            "animate": True,
            "cards": [
                ("RTL to final", "about 3 minutes"),
                ("again, unchanged", "0.4 s"),
            ],
            "select": [0, 1],
            "headline": {0: "Build it", 1: "From the cache"},
        },
        [
            "Build it. Once the tools are built, it takes about three minutes from RTL to final.",
            "Build it again, and the answer comes from the cache, in under a second.",
        ],
    ),
    (
        "terminal",
        {"lines": EXPORT, "show": [3, 5], "headline": "Off: export"},
        [
            "Export takes it back out, as a plain ORFS design.",
            "Make it as usual, in ORFS, on any machine.",
        ],
    ),
    (
        "cards",
        {
            "animate": True,
            "cards": [("Bazel", "5_route.odb"), ("ORFS make", "the same bytes")],
            "select": [1],
            "headline": "The same result",
        },
        ["With the same ORFS and tools, make gives a byte-identical result."],
    ),
    (
        "title",
        {
            "title": "Try it in a clone.",
            "sub": "One install: bazelisk.   github.com/The-OpenROAD-Project/bazel-orfs",
        },
        ["Try it in a clone of bazel-orfs, the quickest way to look around."],
    ),
]

SCRIPTS = {"full": TALK, "sample": [ON], "words": pronunciation.words_scenes()}
