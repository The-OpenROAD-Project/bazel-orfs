"""Run one timing model or one shard: plan its inputs, then sta.sh.

    run.py model <tree.json> <module> <sta.sh> <sta> <script> <libs.tar> <model.lib> <stats.json>
    run.py shard <tree.json> <shards.json> <glue> <shard> <sta.sh> <sta> <script>
                 <libs.tar> <rows> <paths> <stats.json> <path count> [<listed name>=<model.lib>...]

A model reads the module's subtree. A shard reads what plan.shard_plan
gives it, and fails when a model it needs is not among the models given.
"""

import os
import subprocess
import sys

import plan


def run(sta_sh, sta, script, libs_tar, env):
    full = dict(os.environ)
    full.update(env)
    subprocess.run(["bash", sta_sh, sta, script, libs_tar], env=full, check=True)


def model(argv):
    tree_json, name, sta_sh, sta, script, libs_tar, lib, stats = argv
    tree = plan.load(tree_json)
    module = plan.resolve_one(tree, name)
    run(
        sta_sh,
        sta,
        script,
        libs_tar,
        {
            "PSTA_NETLIST": " ".join(plan.files(tree, plan.subtree(tree, module))),
            "PSTA_TOP": module,
            "PSTA_MODEL": lib,
            "PSTA_STATS": stats,
        },
    )


def shard(argv):
    (
        tree_json,
        shards_json,
        glue,
        name,
        sta_sh,
        sta,
        script,
        libs_tar,
        rows,
        paths,
        stats,
        count,
    ) = argv[:12]
    tree = plan.load(tree_json)
    shards = plan.load(shards_json)
    available = {}
    for pair in argv[12:]:
        listed, lib = pair.split("=", 1)
        available[plan.resolve_one(tree, listed)] = lib
    netlist, modelled, here, elsewhere = plan.shard_plan(tree, shards, glue, name)
    libs = [available[m] for m in modelled if m in available]
    missing = [m for m in modelled if m not in available]
    if missing:
        raise SystemExit(
            "shard %s reads %s as timing models, and the models list does not have them"
            % (name, ", ".join(missing))
        )
    sys.stderr.write(
        "shard %s: netlists %s; models %s; lists %s\n"
        % (name, " ".join(netlist), " ".join(modelled), " ".join(here))
    )
    run(
        sta_sh,
        sta,
        script,
        libs_tar,
        {
            "PSTA_NETLIST": " ".join(plan.files(tree, netlist)),
            "PSTA_MODELS": " ".join(libs),
            "PSTA_MODEL_CELLS": " ".join(modelled),
            "PSTA_TOP": tree["top"],
            "PSTA_LISTED": " ".join(here),
            "PSTA_LISTED_ELSEWHERE": " ".join(elsewhere),
            "PSTA_GLUE": "1" if name == glue else "0",
            "PSTA_ROWS": rows,
            "PSTA_PATHS": paths,
            "PSTA_STATS": stats,
            "PSTA_PATH_COUNT": count,
        },
    )


if __name__ == "__main__":
    {"model": model, "shard": shard}[sys.argv[1]](sys.argv[2:])
