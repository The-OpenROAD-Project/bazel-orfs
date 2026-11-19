"""Run one timing model: plan its inputs, then sta.sh.

    run.py model <tree.json> <module> <sta.sh> <sta> <script> <libs.tar> <model.lib> <stats.json>

A model reads the module's subtree.
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


if __name__ == "__main__":
    {"model": model}[sys.argv[1]](sys.argv[2:])
