"""The pronunciation dictionary against the pinned voice and the scripts.

argv: the voice's .onnx.json, then the video scripts.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pronunciation  # noqa: E402

CONFIG, SCRIPTS = sys.argv[1], sys.argv[2:]

# Words no video says yet, checked ahead for the ones that will.
AHEAD = {"Yosys", "asap7"}


class PronunciationTest(unittest.TestCase):
    def test_every_phoneme_is_the_voices(self):
        with open(CONFIG) as f:
            known = set(json.load(f)["phoneme_id_map"])
        for word, (phonemes, _) in pronunciation.WORDS.items():
            missing = sorted(set(phonemes) - known)
            self.assertEqual(
                missing, [], "{}: {} not in the voice".format(word, missing)
            )

    def test_every_word_is_said_or_checked_ahead(self):
        text = "".join(open(p).read() for p in SCRIPTS)
        for word in pronunciation.WORDS:
            if word not in AHEAD:
                self.assertIn(word, text, "no script says {}: drop it".format(word))

    def test_longest_word_wins(self):
        self.assertEqual(
            pronunciation.say("bazel-orfs helps you with ORFS."),
            "[[ bˈeɪzəlˌoʊˌɑːɹˌɛfˈɛs ]] helps you with [[ ˌoʊˌɑːɹˌɛfˈɛs ]].",
        )

    def test_whole_words_only(self):
        self.assertEqual(pronunciation.say("ORFS's make"), "[[ ˌoʊˌɑːɹˌɛfˈɛs ]]'s make")
        self.assertEqual(pronunciation.say("AIR and FAIRY"), "AIR and FAIRY")


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
