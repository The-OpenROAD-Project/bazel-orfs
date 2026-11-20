#!/usr/bin/env python3
"""Which stages of //test/options_structs:accumulator does an edit run again?

Run from the workspace root:

    python3 test/options_structs/stage_keys.py \
        '"slew_margin": 10' '"slew_margin": 12'

Replaces the first text with the second in test/options_structs/BUILD.bazel,
asks bazel for the package's actions before and after, and puts the file
back. Nothing is built.

An action's key covers its command line, its environment and, for a file a
rule writes at analysis, the content; it does not cover the content of its
inputs. So the key of the action that writes a stage's .odb is hashed here
together with the keys of every action of the package it reads from,
transitively. A stage whose hash is the same gets the same inputs and bazel
does not run it again; the other actions of a stage's target that changed
(the scripts `bazelisk run` uses, say) are counted beside it.
"""

import hashlib
import json
import pathlib
import subprocess
import sys

BUILD = pathlib.Path("test/options_structs/BUILD.bazel")
PACKAGE = "//test/options_structs"
RESULTS = [
    ("synth", "1_synth.odb"),
    ("floorplan", "2_floorplan.odb"),
    ("place", "3_place.odb"),
    ("cts", "4_cts.odb"),
    ("grt", "5_1_grt.odb"),
]


def stage_hashes():
    out = subprocess.run(
        [
            "bazelisk",
            "aquery",
            "--output=jsonproto",
            'filter("^{}:", deps({}:accumulator_grt))'.format(PACKAGE, PACKAGE),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    ).stdout
    graph = json.loads(out)
    fragments = {f["id"]: f for f in graph.get("pathFragments", [])}
    depsets = {d["id"]: d for d in graph.get("depSetOfFiles", [])}
    targets = {t["id"]: t["label"] for t in graph.get("targets", [])}

    def basename(artifact):
        return fragments[artifact["pathFragmentId"]]["label"]

    names = {a["id"]: basename(a) for a in graph.get("artifacts", [])}
    actions = graph.get("actions", [])
    producer = {}
    for action in actions:
        for output in action.get("outputIds", []):
            producer[output] = action

    depset_artifacts = {}

    def artifacts_of(depset_id):
        if depset_id not in depset_artifacts:
            depset = depsets[depset_id]
            found = set(depset.get("directArtifactIds", []))
            for child in depset.get("transitiveDepSetIds", []):
                found |= artifacts_of(child)
            depset_artifacts[depset_id] = found
        return depset_artifacts[depset_id]

    deep = {}

    def deep_key(action):
        ident = id(action)
        if ident not in deep:
            digest = hashlib.sha256(action["actionKey"].encode())
            inputs = set()
            for depset_id in action.get("inputDepSetIds", []):
                inputs |= artifacts_of(depset_id)
            for key in sorted(deep_key(producer[i]) for i in inputs if i in producer):
                digest.update(key.encode())
            deep[ident] = digest.hexdigest()
        return deep[ident]

    sys.setrecursionlimit(10000)
    hashes = {}
    for stage, result in RESULTS:
        (action,) = [
            a for a in actions if result in [names[o] for o in a.get("outputIds", [])]
        ]
        label = targets[action["targetId"]]
        others = {
            ",".join(sorted(names[o] for o in a.get("outputIds", []))): a["actionKey"]
            for a in actions
            if targets[a["targetId"]] == label and a is not action
        }
        hashes[stage] = (deep_key(action)[:12], others)
    return hashes


def main():
    old, new = sys.argv[1:3]
    text = BUILD.read_text()
    if text.count(old) != 1:
        sys.exit("{!r} is in {} {} times, not once".format(old, BUILD, text.count(old)))
    before = stage_hashes()
    BUILD.write_text(text.replace(old, new))
    try:
        after = stage_hashes()
    finally:
        BUILD.write_text(text)
    print(
        "{:10} {:12}  {:12}  {:7}  {}".format(
            "stage",
            "before",
            "after",
            "runs",
            "other actions of the target that changed",
        )
    )
    for stage, _ in RESULTS:
        changed = sorted(
            name
            for name, key in before[stage][1].items()
            if after[stage][1].get(name) != key
        )
        print(
            "{:10} {:12}  {:12}  {:7}  {}".format(
                stage,
                before[stage][0],
                after[stage][0],
                "again" if before[stage][0] != after[stage][0] else "no",
                " ".join(changed) or "-",
            )
        )


if __name__ == "__main__":
    main()
