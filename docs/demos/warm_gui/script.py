"""Around the EDA World in N Minutes: what is shown and what is said.

A scene is (kind, options, sentences). The kind picks its picture in
video.py; each sentence is spoken and burned in as one caption, and the
scene lasts as long as its sentences. Scenes that build up ("show",
"states", "lit", "light") change with each sentence. "{N}" is the video's
own length, settled by video.py once the narration is spoken.

The frame is Jules Verne's (1872, public domain): you are Phileas Fogg,
bazel-orfs is Passepartout ("goes everywhere"), and Inspector Fix is the
AI reviewer who suspects everything. Audience questions carry the role
of who would ask them.

FULL is the talk, landscape; SHORT the cell-phone cut. The commands are
the ones run on ORFS's asap7 gcd and aes-block; 10.7.0.3 stands for the
viewer's VPN address and is made up, as the frames say.
"""

TITLE = "Around the EDA World in {N}"

# Written form -> spoken form, for the narrator.
SAY = [
    ("bazel-orfs's", "bazel orfs's"),
    ("bazel-orfs", "bazel orfs"),
    ("@bazel-orfs//:bump", "bazel orfs bump"),
    ("bazelisk", "bazel-isk"),
    ("make gui_final", "make gooey final"),
    ("orfs_flow", "orfs flow"),
    ("config.mk", "config dot M K"),
    ("odb-debug", "O D B debug"),
    ("OpenROAD", "Open Road"),
    ("MODULE.bazel", "the module file"),
    ("Passepartout", "Pass-par-too"),
    ("Phileas Fogg", "Fileas Fogg"),
    ("yosys", "yo-sis"),
    ("asap7", "A sap seven"),
    ("Optuna", "Op-tuna"),
    ("ORFS", "orfs"),
    ("RTL", "R T L"),
    ("PDK", "P D K"),
    ("MCP", "M C P"),
    ("VPN", "V P N"),
    ("GUI", "gooey"),
    ("EDA", "E D A"),
    ("Tcl", "tickle"),
    ("AES", "A E S"),
    ("gcd", "G C D"),
    ("+0.24", "plus zero point two four"),
]


def say(text):
    for written, spoken in SAY:
        text = text.replace(written, spoken)
    return text


# Who is who: the cast, then the passengers, one letter each.
PEOPLE = [
    ("fogg", "Phileas Fogg: you"),
    ("passepartout", "Passepartout: bazel-orfs"),
    ("fix", "Inspector Fix: the AI reviewer"),
    ("dan", "Dan the Doubter"),
    ("sam", "Sam the Student"),
    ("otto", "Otto the ORFS user"),
    ("arthur", "Arthur the Architect"),
    ("basil", "Basil the Bazel expert"),
    ("rita", "Rita the Researcher"),
    ("maya", "Maya the Maintainer"),
    ("tara", "Tara the Tapeout engineer"),
    ("priya", "Priya the Prompt engineer"),
]
NAME = dict(PEOPLE)
PASSENGERS = ["dan", "sam", "otto", "arthur", "basil", "rita", "maya", "tara", "priya"]

VPN = "10.7.0.3: your VPN address (made up for this video)"
SERVER = "Server, 10.7.0.3 (your VPN address, made up)"
# A GUI screenshot's layout panel, as fractions of width and height: a
# phone shows that, not the whole page.
CROP = [0.155, 0.055, 0.70, 0.705]

CHORES = [
    "build OpenROAD",
    "build yosys",
    "find versions that agree",
    "set up the PDK",
    "synthesis again: you moved a placement knob",
    "wait for the GUI",
]

ROUTES = ["Student", "Design space", "Hyperparameters", "Maintainer", "Tapeout", "AI"]

STUDENT = [
    "$ bazelisk build @orfs//flow/designs/asap7/gcd:gcd_final",
    "$ bazelisk run //:dirty -- start @orfs//flow/designs/asap7/gcd:gcd final",
    "$ cd tmp/orfs/flow/designs/asap7/gcd/gcd",
    "$ ./make do-final",
    "$ ./make gui_final",
    "odb-debug: open the GUI: http://10.7.0.3:33321/?token=...",
]

FLOW = [
    'load("@bazel-orfs//:openroad.bzl", "orfs_flow")',
    "",
    "orfs_flow(",
    '    name = "mac",',
    '    verilog_files = ["mac.v"],',
    '    sources = {"SDC_FILE": [":constraints.sdc"]},',
    '    arguments = {"CORE_UTILIZATION": "40", "PLACE_DENSITY": "0.65"},',
    ")",
]

STAGES = ["synth", "floorplan", "place", "cts", "grt", "route", "final"]
ALL = ["cached"] * 7
KNOB = ["cached", "cached", "rerun", "rerun", "rerun", "rerun", "rerun"]

AGENT = [
    "> build grt aes-blocks asap7",
    "Built @orfs//flow/designs/asap7/aes-block:aes_cipher_top_grt",
    "  WNS 0.00  TNS 0.00  worst slack +0.24",
    "Loading it into odb-debug for you...",
    "GUI ready: http://10.7.0.3:42459/?token=...",
]

CONTEXT = [
    "Tokens cost money, on every turn",
    "Tokens cost time, on every turn",
    "Irrelevant tokens lower quality: the model loses the thread and fills the gaps",
]

PROMPT = [
    "> look at bazel-orfs, make an MCP server for our project",
    "  that saves tokens, time and avoids context explosion",
]


def q(who, question, said, **opts):
    """A passenger's question: the asker and the bubble on screen, the
    question spoken first, then the answer."""
    return (
        "qa",
        dict(opts, who=who, role=NAME[who], question=question),
        ["%s asks: %s" % (NAME[who], question)] + said,
    )


FULL = [
    # Welcome: how the story goes, and who is in it.
    (
        "cast",
        {"heading": "Welcome aboard", "cast": ["fogg", "passepartout", "fix"]},
        [
            "Welcome aboard. This talk is a story, because stories keep people awake. That is the joke, and also the point.",
            "You are Phileas Fogg. bazel-orfs is your Passepartout. And keep an eye on Inspector Fix.",
        ],
    ),
    (
        "cast",
        {"heading": "Your fellow passengers", "cast": PASSENGERS},
        [
            "And your fellow passengers: Dan the Doubter, Sam the Student, Otto the ORFS user, Arthur the Architect, Basil the Bazel expert, Rita the Researcher, Maya the Maintainer, Tara the Tapeout engineer, and Priya the Prompt engineer.",
            "They will interrupt with the questions you would ask.",
        ],
    ),
    # Prologue: the chores.
    (
        "trunk",
        {"items": CHORES, "show": [0, 6], "figures": [("fogg", "right", "watch")]},
        [
            "Phileas Fogg did not pack his own trunk.",
            "Yet before you can learn anything from OpenROAD, you pack for days: build the tools, find versions that agree, set up the PDK, run synthesis again because you moved a placement knob, and wait for the GUI.",
        ],
    ),
    (
        "trunk",
        {
            "items": CHORES,
            "show": [6],
            "struck": True,
            "answer": "$ install bazelisk",
            "figures": [("passepartout", "right", "carry")],
        },
        [
            'Meet your Passepartout: bazel-orfs. The name is French for "goes everywhere".',
            "He packs, he books, he fetches. You choose the journey.",
        ],
    ),
    (
        "title",
        {
            "sub": "One install, many journeys",
            "figures": [("fogg", "left", "tip"), ("passepartout", "right", "carry")],
        },
        ["Around the EDA world in {N}."],
    ),
    q(
        "dan",
        "One install? I've heard that before.",
        [
            "The first time, Passepartout builds everything from source, and that takes a while. After that, nothing is built twice, and with a shared cache, not even once on your machine.",
        ],
    ),
    # The voyage map.
    (
        "voyage",
        {"routes": ROUTES, "hub": "You are here: bazelisk"},
        [
            "From here, the routes go everywhere.",
            "Every route uses two lanes. The hermetic lane is for solved problems: pinned, cached, the same answer on any machine. The dirty lane is for unsolved ones: a plain ORFS tree, where you edit Tcl and rerun a stage in minutes.",
            "Both are good. Explore dirty; once you know the answer, wrap it up hermetically.",
        ],
    ),
    # Port 1: the student route.
    (
        "voyage",
        {"routes": ROUTES, "hub": "You are here: bazelisk", "lit": [0], "fogg": 0},
        ["First port: the student route. Build it, look at it, change it."],
    ),
    (
        "terminal",
        {
            "lines": STUDENT,
            "show": [2, 6],
            "note": VPN,
            "figures": [("fogg", "right", "watch")],
        },
        [
            "A small design, gcd: build it, then lay it out in a tree of your own, and run the final stage by hand.",
            "make gui_final loads it into OpenROAD, headless, and prints a link.",
        ],
    ),
    (
        "image",
        {
            "image": "gcd",
            "label": "gcd, routed, in your browser",
            "figures": [("fogg", "right", "tip")],
        },
        ["That is gcd, routed, in OpenROAD's GUI, in your browser."],
    ),
    q(
        "sam",
        "Do I have to learn Bazel?",
        [
            "No. Bazel sounds scary, and it solves hard problems, but it doesn't change how you work.",
            "Your AI writes the BUILD files you need; you review the diff. What you need is a picture of what you want.",
        ],
    ),
    q(
        "sam",
        "Where does my own design go?",
        [
            "Into a few lines next to your RTL: orfs_flow takes your Verilog, your constraints and ORFS's own settings, and makes one target per stage.",
        ],
        lines=FLOW,
    ),
    q(
        "otto",
        "I already have a config.mk. Do I rewrite it?",
        [
            "No. A domain-specific language is a small language for one job, and config.mk is one: a few make variables that say what a design is.",
        ],
    ),
    (
        "mapping",
        {
            "heading": "config.mk, read by bazel-orfs",
            "rows": [
                ("DESIGN_NAME, PLATFORM", "the flow's name and PDK"),
                ("VERILOG_FILES, SDC_FILE, PDN_TCL, ...", "its sources, as labels"),
                ("every other variable", "its settings"),
                ("BLOCKS", "its macros, each from its own config.mk"),
            ],
        },
        [
            "bazel-orfs reads it as it stands, so every ORFS design, from gcd up, is already a flow you can build.",
        ],
    ),
    # Port 2: the design-space route.
    (
        "voyage",
        {"routes": ROUTES, "hub": "You are here: bazelisk", "lit": [1], "fogg": 1},
        ["Second port: design space. What does your RTL really cost?"],
    ),
    (
        "stages",
        {
            "stages": STAGES,
            "states": [ALL, KNOB],
            "figures": [("passepartout", "right", "carry")],
        },
        [
            "Every stage is one Bazel action, keyed by exactly what it reads.",
            "Change a placement setting, and synthesis and floorplan come from the cache; only placement onward runs again.",
        ],
    ),
    (
        "table",
        {
            "heading": "orfs_sweep: design points as targets",
            "header": ["design point", "PLACE_DENSITY", "target"],
            "rows": [
                ["base", "0.65", "//my:mac_final"],
                ["dense", "0.80", "//my:mac_dense_final"],
                ["loose", "0.50", "//my:mac_loose_final"],
            ],
        },
        [
            "So sweep: tens of design points as targets, built in parallel, each one cached. Change one, and only it is rebuilt.",
        ],
    ),
    q(
        "arthur",
        "What does my RTL change cost in area and timing?",
        [
            "Make the change a design point, and the sweep answers it next to every other point, from the same pinned tools.",
        ],
    ),
    # Port 3: the hyperparameter route.
    (
        "voyage",
        {"routes": ROUTES, "hub": "You are here: bazelisk", "lit": [2], "fogg": 2},
        ["Third port: hyperparameters. Here, Bazel steps aside."],
    ),
    (
        "lanes",
        {
            "lanes": [
                (
                    "Bazel loop",
                    ["tens of design points", "cached targets", "orfs_sweep"],
                ),
                (
                    "Optimizer loop",
                    [
                        "thousands of trials",
                        "one executable, built once",
                        "orfs_run_executable",
                    ],
                ),
            ],
            "light": {0: 1},
        },
        [
            "Bazel builds one standalone executable of the flow, once. Optuna, or any optimizer, calls it in its own loop with new settings each time.",
        ],
    ),
    q(
        "basil",
        "Why not just call bazel build from the optimizer?",
        [
            "Each call pays Bazel's own overhead, and every new setting re-keys every stage that reads it. A build system is the wrong tool for a trial loop; its job is to make the executable the same everywhere.",
        ],
    ),
    (
        "tree",
        {
            "heading": "fork: shared stages, paid once",
            "root": "synth, floorplan, place: shared",
            "leaves": ["trial 1", "trial 2", "trial 3", "trial 4"],
        },
        [
            "When trials share their first stages, one OpenROAD process walks the whole tree, and pays each shared stage once.",
        ],
    ),
    q(
        "rita",
        "Is there a worked example?",
        [
            "The estimation ladder in bazel-orfs: an Optuna study that trades an estimator's runtime against its accuracy, checked against a full global route.",
        ],
    ),
    # Port 4: the maintainer route.
    (
        "voyage",
        {"routes": ROUTES, "hub": "You are here: bazelisk", "lit": [3], "fogg": 3},
        ["Fourth port: the maintainer route. Carry it, prove it, propose it."],
    ),
    (
        "bullets",
        {
            "heading": "Every tool: a pinned archive with a patches list",
            "items": [
                "bazel-orfs",
                "OpenROAD, built from source",
                "ORFS: flow scripts and platforms",
                "yosys, the slang frontend, the PDK",
            ],
        },
        [
            "Every tool is a pinned archive with a list of patches, so a fix can be carried until upstream takes it."
        ],
    ),
    (
        "bullets",
        {
            "heading": "Carry it, prove it, propose it",
            "items": [
                "Ask the AI for a fix, carried as a patch",
                "Sweep the ORFS designs; the AI reports on what you fixed",
                "You read the data, and you decide",
                "A draft upstream pull request, with the data",
            ],
            "show": [2, 4],
        },
        [
            "The ORFS designs are a test bench the maintainers know by heart. Carry a fix, sweep them, and have your AI report the result.",
            "You read the data and decide. Then a draft pull request goes upstream, data included.",
        ],
    ),
    (
        "fix",
        {
            "who": "Inspector Fix, the AI reviewer",
            "claim": "This can return undefined; return Promise.resolve(null) instead.",
            "verdicts": [
                "Check it against the code.",
                "Not taken: the fallback below returns a Promise.",
            ],
        },
        [
            "And then Inspector Fix arrives: the AI reviewer, who suspects everything.",
            "Trust him, but verify every claim he makes.",
        ],
    ),
    q(
        "maya",
        "So we'll get floods of AI pull requests?",
        [
            "No. A human reads the sweep and decides; the pull request carries the data; and the carried patch stays put while you review, so nothing is rushed upstream.",
        ],
    ),
    q(
        "basil",
        "How are the versions kept current?",
        [
            "One command, bazelisk run @bazel-orfs//:bump, moves every pin forward together."
        ],
    ),
    # Port 5: tapeout.
    (
        "voyage",
        {"routes": ROUTES, "hub": "You are here: bazelisk", "lit": [4], "fogg": 4},
        [
            "Fifth port: tapeout. Few take this route, but the track is there: every tool pinned, every result reproducible, the same answer next year as today."
        ],
    ),
    q(
        "tara",
        "Can I prove what produced a result?",
        [
            "Yes. The pins in MODULE.bazel and the patches beside them say exactly what built it."
        ],
    ),
    # Port 6: AI.
    (
        "voyage",
        {"routes": ROUTES, "hub": "You are here: bazelisk", "lit": [5], "fogg": 5},
        ["Last port: AI. A warm session, and a small context."],
    ),
    (
        "terminal",
        {
            "lines": AGENT,
            "show": [5],
            "note": VPN,
            "figures": [("passepartout", "right", "carry")],
        },
        [
            "Ask your agent for a build: global route of the AES block design. It reports the result, and unasked, loads it into a warm, headless OpenROAD session."
        ],
    ),
    (
        "system",
        {"server": SERVER},
        [
            "The flow runs on a powerful server; you sit at a laptop. Over your VPN, the link reaches a small proxy that lets only its token through."
        ],
    ),
    (
        "image",
        {
            "image": "gui",
            "label": "aes-block, global route, one click away",
            "figures": [("passepartout", "left", "point"), ("fogg", "right", "tip")],
        },
        ["One click, and the design is there."],
    ),
    (
        "bullets",
        {
            "heading": "Keep the context small and relevant",
            "items": CONTEXT,
            "show": [0, 3, 3],
        },
        [
            "The agent asks the same session through an MCP server: a question in, a summary out.",
            "Why summaries? Every token in an agent's context costs money and time, and irrelevant ones lower the quality: the model loses the thread and fills the gaps.",
            "And because the design is already loaded, it answers in seconds, not minutes.",
        ],
    ),
    q(
        "priya",
        "Is there a generic OpenROAD MCP server?",
        [
            "You can use one, but on a large project your questions soon become your project's own.",
            "bazel-orfs's server is small and project-specific, a little more than a configuration example. Copy it, or have your AI write yours.",
        ],
    ),
    (
        "terminal",
        {"lines": PROMPT, "show": [2]},
        [
            "Ask your AI to look at bazel-orfs and make one for your project. You review what it writes."
        ],
    ),
    # Epilogue: the day gained.
    (
        "voyage",
        {"routes": ROUTES, "hub": "Home: a day gained", "pose": "tip"},
        [
            "Fogg came home thinking he had lost the wager, then found he had gained a day without noticing.",
            "Your cache does the same: every stage already built is time you get back.",
        ],
    ),
    (
        "title",
        {
            "sub": "Install bazelisk. Choose your journey.  github.com/The-OpenROAD-Project/bazel-orfs",
            "figures": [("fogg", "left", "tip"), ("passepartout", "right", "wave")],
        },
        ["Install bazelisk. Choose your journey."],
    ),
]

SHORT = [
    (
        "cast",
        {"heading": "Welcome aboard", "cast": ["fogg", "passepartout", "fix"]},
        [
            "Welcome aboard: this is a story, so you stay awake. You are Phileas Fogg; bazel-orfs is your Passepartout."
        ],
    ),
    (
        "trunk",
        {"items": CHORES, "show": [6]},
        [
            "Before you can learn anything from OpenROAD, you pack for days: build the tools, find versions that agree, and wait for the GUI."
        ],
    ),
    (
        "trunk",
        {
            "items": CHORES,
            "show": [6],
            "struck": True,
            "answer": "$ install bazelisk",
            "figures": [("passepartout", "right", "carry")],
        },
        [
            'Meet your Passepartout, French for "goes everywhere": bazel-orfs. He packs, he books, he fetches. You choose the journey.'
        ],
    ),
    (
        "title",
        {
            "sub": "One install, many journeys",
            "figures": [("fogg", "left", "tip"), ("passepartout", "right", "carry")],
        },
        ["Around the EDA world in {N}."],
    ),
    (
        "voyage",
        {"routes": ROUTES, "hub": "You are here: bazelisk"},
        [
            "Every route has two lanes: hermetic for solved problems, dirty for the ones you are still exploring."
        ],
    ),
    (
        "terminal",
        {"lines": STUDENT, "show": [6], "note": VPN},
        [
            "Build a design, lay it out in a tree of your own, and make gui_final prints a link."
        ],
    ),
    (
        "image",
        {
            "image": "gcd",
            "label": "gcd, routed, in your browser",
            "portrait_crop": CROP,
        },
        ["That is gcd, routed, in OpenROAD's GUI, in your browser."],
    ),
    (
        "stages",
        {"stages": STAGES, "states": [KNOB]},
        [
            "Change a setting, and only the stages it touches run again: sweep tens of design points, every one cached."
        ],
    ),
    (
        "bullets",
        {
            "heading": "Keep the context small and relevant",
            "items": CONTEXT,
            "show": [3],
        },
        [
            "Your AI asks a warm OpenROAD session for summaries, not logs: every token costs money and time, and irrelevant ones lower the quality."
        ],
    ),
    (
        "title",
        {"sub": "Install bazelisk. Choose your journey."},
        ["Install bazelisk. Choose your journey."],
    ),
]

SCRIPTS = {"full": FULL, "short": SHORT}
