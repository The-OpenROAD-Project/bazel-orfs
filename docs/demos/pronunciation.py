"""How the demo videos' narrator says this project's words.

The narrator is Piper, which turns text into phonemes with espeak-ng.
espeak guesses at acronyms and project names, and a respelling only gives
it something else to guess at: "bazel-isk" came out stressed twice. So the
words below go to the voice as phonemes, in Piper's raw-phoneme syntax
`[[ ... ]]`, the same for every video. Every phoneme must be one the
pinned voice has; pronunciation_test checks that.

To check a word: `bazelisk run //docs/demos/ramps:save_words -- <dir>`
speaks each one.
"""

import re

# written -> (phonemes for the voice, what it sounds like)
WORDS = {
    "ORFS": ("ˈoʊ ˈɑːɹ ˈɛf ˈɛs", "O-R-F-S"),
    "bazel-orfs": ("bˈeɪzəl ˈoʊ ˈɑːɹ ˈɛf ˈɛs", "BAY-zel O-R-F-S"),
    "bazelisk": ("bˈeɪzəlɪsk", "BAY-zuh-lisk"),
    "byte-identical": ("bˈaɪt aɪdˈɛntɪkəl", "byte identical"),
    "asap7": ("ˈeɪsæp sˈɛvən", "AY-sap seven"),
    "Yosys": ("jˈoʊsɪs", "YO-sis"),
    "config.mk": ("kənfˈɪɡ dˈɑːt ˈɛm kˈeɪ", "config dot M K"),
    "AI": ("ˌeɪˈaɪ", "A-I"),
    "RTL": ("ˌɑːɹtˌiːˈɛl", "R-T-L"),
}

# Longest first, so bazel-orfs is one word and not bazel- and ORFS; whole
# words only, so ORFS's is ORFS and a word that merely contains one is not.
_PATTERN = re.compile(
    r"(?<![\w-])("
    + "|".join(re.escape(w) for w in sorted(WORDS, key=len, reverse=True))
    + r")(?![\w-])"
)


def say(text):
    """`text` with each of WORDS as the phonemes the voice reads."""
    return _PATTERN.sub(lambda m: "[[ {} ]]".format(WORDS[m.group(1)][0]), text)


def words_scenes():
    """One title scene per word: the word, what it sounds like, spoken."""
    return [
        ("title", {"title": written, "sub": sounds}, [written])
        for written, (_, sounds) in WORDS.items()
    ]
