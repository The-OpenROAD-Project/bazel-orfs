"""The warm-gui demo: what is shown and what is said.

A scene is (kind, options, sentences). The kind picks its picture in
video.py; each sentence is spoken and burned in as one caption, and the
scene lasts as long as its sentences. Terminal scenes reveal one more
line per sentence (options "show": lines visible at each sentence).

FULL is the landscape video, SHORT the cell-phone one. Every claim is
what bazel-orfs #1300 does and what the aes-block build printed.
"""

TITLE = "The GUI, warm and one click away"

# Written form -> spoken form, for the narrator.
SAY = [
    ("aes_cipher_top_grt", "the A E S block's global route"),
    ("odb-debug", "O D B debug"),
    ("bazel-orfs", "bazel orfs"),
    ("OpenROAD", "Open Road"),
    ("asap7", "A sap seven"),
    ("MCP", "M C P"),
    ("VPN", "V P N"),
    ("ssh", "S S H"),
    ("Tcl", "tickle"),
    ("GUI", "gooey"),
    ("+0.24", "plus zero point two four"),
]


def say(text):
    for written, spoken in SAY:
        text = text.replace(written, spoken)
    return text


PROMPT = "> build grt aes-blocks asap7"
REPLY = [
    "Built @orfs//flow/designs/asap7/aes-block:aes_cipher_top_grt",
    "  WNS 0.00  TNS 0.00  worst slack +0.24",
    "Loading it into odb-debug for you...",
    "GUI ready: http://10.8.0.5:42459/?token=...",
]

FULL = [
    (
        "title",
        {},
        [
            "On a large design, OpenROAD's GUI takes tens of minutes to load.",
            "bazel-orfs now hides that wait behind the build.",
        ],
    ),
    (
        "terminal",
        {"lines": [PROMPT], "show": [1]},
        [
            "You ask the agent for a build: global route of the AES block design, on asap7.",
        ],
    ),
    (
        "terminal",
        {"lines": [PROMPT] + REPLY, "show": [3, 4, 5]},
        [
            "The build finishes with a worst slack of +0.24.",
            "Without being asked, the agent loads the result into an odb-debug daemon, while you read it.",
            "Its reply ends with a link to the GUI.",
        ],
    ),
    (
        "diagram",
        {},
        [
            "The link goes through a small proxy on the address your ssh session came in on, so it works over a VPN.",
            "Only requests carrying the link's token reach the viewer, because the viewer runs any Tcl it is sent.",
        ],
    ),
    (
        "image",
        {"image": "gui", "label": "Click the link: the design is already loaded"},
        [
            "Click the link, and the design is already there.",
            "The agent asks its own questions of the same session, through the MCP server.",
        ],
    ),
    (
        "image",
        {
            "image": "layout",
            "label": "Drawn headless by the build that made this video",
        },
        [
            "This is the same global route, drawn headless inside the build that made this video.",
        ],
    ),
    (
        "bullets",
        {
            "items": [
                "Waits for its first visitor, with no idle exit",
                "Then exits when nobody has asked or browsed for a while",
                "Every build ends with a warm GUI: the warm-gui skill",
            ]
        },
        [
            "The daemon waits for its first visitor with no idle exit.",
            "After that, it exits once nobody has asked or browsed for a while.",
            "Every build now ends with a warm GUI.",
        ],
    ),
    (
        "title",
        {"sub": "bazelisk run @bazel-orfs//:agent -- setup"},
        [
            "Consumers get it through bazel-orfs's agent channel.",
        ],
    ),
]

SHORT = [
    (
        "title",
        {},
        [
            "OpenROAD's GUI can take tens of minutes to load.",
        ],
    ),
    (
        "terminal",
        {"lines": [PROMPT] + REPLY, "show": [1, 3, 5]},
        [
            "Ask the agent for a build.",
            "It finishes with a worst slack of +0.24.",
            "And, unasked, the agent loads it into the GUI for you.",
        ],
    ),
    (
        "image",
        {
            "image": "gui",
            "label": "One click: already loaded",
            # gui.png's layout panel, as fractions of its width and height
            "portrait_crop": [0.155, 0.055, 0.70, 0.705],
        },
        [
            "One click, over your VPN, and the design is there.",
        ],
    ),
    (
        "title",
        {"sub": "bazel-orfs: the warm-gui skill"},
        [
            "Every build ends with a warm GUI.",
        ],
    ),
]

SCRIPTS = {"full": FULL, "short": SHORT}
