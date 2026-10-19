"""The bazel-orfs demo: what is shown and what is said.

A scene is (kind, options, sentences). The kind picks its picture in
video.py; each sentence is spoken and burned in as one caption, and the
scene lasts as long as its sentences. Terminal and bullet scenes reveal
lines as the sentences go ("show": lines visible at each sentence); a
lanes scene lights the lane a sentence is about ("light": sentence ->
lane).

FULL is the landscape video, SHORT the cell-phone one. The commands are
the ones run on ORFS's asap7 gcd and aes-block; 10.7.0.3 stands for the
viewer's VPN address and is made up, as the frames say.
"""

TITLE = "bazel-orfs: work your own way"

# Written form -> spoken form, for the narrator.
SAY = [
    ("bazel-orfs's", "bazel orfs's"),
    ("bazel-orfs", "bazel orfs"),
    ("bazelisk", "bazel-isk"),
    ("make gui_final", "make gooey final"),
    ("odb-debug", "O D B debug"),
    ("OpenROAD", "Open Road"),
    ("yosys", "yo-sis"),
    ("asap7", "A sap seven"),
    ("ORFS", "orfs"),
    ("PDK", "P D K"),
    ("MCP", "M C P"),
    ("VPN", "V P N"),
    ("GUI", "gooey"),
    ("Tcl", "tickle"),
    ("CI", "C I"),
    ("AES", "A E S"),
    ("gcd", "G C D"),
]


def say(text):
    for written, spoken in SAY:
        text = text.replace(written, spoken)
    return text


VPN = "10.7.0.3: your VPN address (made up for this video)"
SERVER = "Server, 10.7.0.3 (your VPN address, made up)"

INSTALL = [
    "$ # the one thing to install: bazelisk",
    "$ bazelisk build @orfs//flow/designs/asap7/gcd:gcd_final",
]

LANES = [
    (
        "Hermetic lane",
        [
            "bazelisk build",
            "cached, reproducible, shared",
            "for solved problems: numbers, CI, colleagues",
        ],
    ),
    (
        "Dirty lane",
        [
            "a plain ORFS tree: make, Tcl",
            "minutes per change, hack anything",
            "for unsolved problems: exploring, debugging",
        ],
    ),
]

DIRTY = [
    "$ bazelisk run //:dirty -- start @orfs//flow/designs/asap7/gcd:gcd final",
    "$ cd tmp/orfs/flow/designs/asap7/gcd/gcd",
    "$ ./make do-final",
    "$ ./make gui_final",
    "odb-debug: open the GUI: http://10.7.0.3:33321/?token=...",
]

AGENT = [
    "> build grt aes-blocks asap7",
    "Built @orfs//flow/designs/asap7/aes-block:aes_cipher_top_grt",
    "  WNS 0.00  TNS 0.00  worst slack +0.24",
    "Loading it into odb-debug for you...",
    "GUI ready: http://10.7.0.3:42459/?token=...",
]

PROMPT = [
    "> look at bazel-orfs, make an MCP server for our project",
    "  that saves tokens, time and avoids context explosion",
]

MCP = [
    "Question in, summary out: no context explosion",
    "Warm: answers in seconds, not minutes",
]

OWN = [
    "Generic OpenROAD MCP: a start",
    "A large project's questions are its own",
    "bazel-orfs's: small, no options, no extension points",
    "Vendor it, extend it, or have your AI write one",
]

# The layout panel of a GUI screenshot, as fractions of width and height:
# a phone shows that, not the whole page.
CROP = [0.155, 0.055, 0.70, 0.705]

END = {"title": "bazel-orfs", "sub": "github.com/The-OpenROAD-Project/bazel-orfs"}

S = {
    1: "bazel-orfs builds OpenROAD flows with Bazel, and lets you work your own way.",
    2: "Installing tools is a solved problem: install bazelisk, and you are done.",
    3: "OpenROAD, yosys, the flow scripts and the PDK are fetched and built for you, at the versions your project pins.",
    4: "Both lanes are good; they are for different problems.",
    5: "The hermetic lane is for solved problems: the results are cached, reproducible, and shared by everyone who builds, so use it for numbers, for CI, and for your colleagues.",
    6: "The dirty lane is for unsolved problems: a plain ORFS tree where you edit Tcl and rerun a stage in minutes, so use it while you explore and debug.",
    7: "Once you know the answer, you wrap it up hermetically.",
    8: "Here is the dirty lane on a small design, gcd: lay out the tree, and run the final stage by hand.",
    9: "Then make gui_final loads the result into a warm, headless OpenROAD session, and prints a link.",
    10: "That is gcd's final layout, in OpenROAD's GUI, in your browser.",
    11: "In the hermetic lane, the agent does the same after every build.",
    12: "Ask it for global route of the AES block design; it reports the result, and unasked, loads it into a warm headless OpenROAD session.",
    13: "The flow runs on a powerful server; you sit at a laptop.",
    14: "Over your VPN, the link reaches a small proxy that lets only the token through, to the session that is already loaded.",
    15: "One click, and the design is there.",
    16: "The agent asks the same session through bazel-orfs's odb-debug MCP server.",
    17: "It takes a question and replies with a summary, so the agent's context does not explode into delusions and cost.",
    18: "And because the design is already loaded, it answers in seconds, not minutes.",
    19: "You can use a generic OpenROAD MCP server, but on a large project your questions soon become specific to that project.",
    20: "bazel-orfs's MCP server is project-specific too. It is small, a little more than a configuration example, with no options and no extension points.",
    21: "So do not wait for it to grow options: vendor it, the licence allows it, or have your AI build your own.",
    22: "This is code an AI writes in one shot; you need not read it.",
    23: "Ask your AI to look at bazel-orfs and make an MCP server for your project that saves tokens and time, and avoids context explosion.",
    24: "bazel-orfs: work your own way, and build on what works.",
}

MCP_HEAD = "bazel-orfs's odb-debug MCP server"
OWN_HEAD = "Your own MCP server"

FULL = [
    ("title", {}, [S[1]]),
    ("terminal", {"lines": INSTALL, "show": [2, 2]}, [S[2], S[3]]),
    ("lanes", {"lanes": LANES, "light": {1: 0, 2: 1}}, [S[4], S[5], S[6], S[7]]),
    ("terminal", {"lines": DIRTY, "show": [3, 5], "note": VPN}, [S[8], S[9]]),
    ("image", {"image": "gcd", "label": "gcd, final, in your browser"}, [S[10]]),
    ("terminal", {"lines": AGENT, "show": [1, 5], "note": VPN}, [S[11], S[12]]),
    ("system", {"server": SERVER}, [S[13], S[14]]),
    (
        "image",
        {"image": "gui", "label": "aes-block, global route, one click away"},
        [S[15]],
    ),
    (
        "bullets",
        {"heading": MCP_HEAD, "items": MCP, "show": [0, 1, 2]},
        [S[16], S[17], S[18]],
    ),
    (
        "bullets",
        {"heading": OWN_HEAD, "items": OWN, "show": [2, 3, 4]},
        [S[19], S[20], S[21]],
    ),
    ("terminal", {"lines": PROMPT, "show": [2, 2]}, [S[22], S[23]]),
    ("title", END, [S[24]]),
]

SHORT = [
    ("title", {}, [S[1]]),
    ("terminal", {"lines": INSTALL, "show": [2]}, [S[2]]),
    ("lanes", {"lanes": LANES}, [S[4], S[7]]),
    ("terminal", {"lines": AGENT, "show": [5], "note": VPN}, [S[12]]),
    ("system", {"server": SERVER}, [S[13]]),
    (
        "image",
        {"image": "gui", "label": "One click: already loaded", "portrait_crop": CROP},
        [S[15]],
    ),
    ("bullets", {"heading": MCP_HEAD, "items": MCP[:1], "show": [1]}, [S[17]]),
    ("bullets", {"heading": OWN_HEAD, "items": OWN[3:], "show": [1]}, [S[21]]),
    ("terminal", {"lines": PROMPT, "show": [2]}, [S[23]]),
    ("title", END, [S[24]]),
]

SCRIPTS = {"full": FULL, "short": SHORT}
