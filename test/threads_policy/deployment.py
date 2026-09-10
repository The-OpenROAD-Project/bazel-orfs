#!/usr/bin/env python3
"""Where a deployed `_deps` tree keeps the files one arm reads and writes.

ORFS puts every derived file under a *variant*:

    results/<platform>/<design>/<variant>/4_1_cts.odb
    logs/<platform>/<design>/<variant>/4_1_cts.log
    objects/<platform>/<design>/<variant>/...

and `FLOW_VARIANT` picks which one. A deployed reproducer arrives with a
single `base` variant holding the previous stage's outputs, and the
#968 harness relied on that: it found the results and logs directories
by walking for the deepest one that contained a `.odb` or a `.log`.

That heuristic is correct for exactly one variant and silently wrong for
two -- it starts returning whichever arm's directory happens to sort
last, so a sample would be read from a *different arm's* files. The
idempotency mode runs several arms at once, each in its own variant, so
the layout has to be addressed rather than guessed.

`FLOW_VARIANT` is declared `export FLOW_VARIANT?=base` in the deployed
`config.mk`, a conditional assignment, so a command-line
`FLOW_VARIANT=<v>` overrides it. Cloning `base` to `<v>` first gives the
arm the previous stage's inputs where it expects them; measured on
nangate45/gcd, three arms then ran concurrently with no interference.
"""

import os
import shutil


class Deployment:
    """The layout of one deployed stage reproducer.

    Resolved once from the tree rather than recomputed per lookup: the
    walk is the expensive part and the answer cannot change while an
    arm runs.
    """

    def __init__(self, root):
        self.root = root
        self.results_root, self.platform, self.design = _locate(root)
        # logs/ and objects/ are siblings of results/ and are created by
        # the run, so they are named here and not required to exist.
        self.work_home = os.path.dirname(self.results_root)
        self.logs_root = os.path.join(self.work_home, "logs")

    def results(self, variant):
        return os.path.join(self.results_root, self.platform, self.design, variant)

    def logs(self, variant):
        return os.path.join(self.logs_root, self.platform, self.design, variant)

    def clone_base(self, variant):
        """Give `variant` its own copy of what `base` holds.

        `base` is mostly symlinks into the Bazel cache, and `copytree`
        with `symlinks=True` keeps them symlinks: the previous stage's
        outputs are inputs here, read-only and shared, so copying their
        bytes per arm would multiply the tree by the number of arms for
        no benefit. Only what the arm writes is new.

        An existing variant directory is removed first. A half-finished
        arm left behind by an interrupted campaign would otherwise be
        read as this arm's result.
        """
        target = self.results(variant)
        if os.path.exists(target):
            shutil.rmtree(target)
        shutil.copytree(self.results(BASE), target, symlinks=True)
        # A stale log directory would let collect() read the previous
        # occupant's log if this arm died before writing its own.
        logs = self.logs(variant)
        if os.path.exists(logs):
            shutil.rmtree(logs)
        return target


BASE = "base"


def arm_variant(threads, repeat):
    """The variant name for one arm. Also its results/logs directory."""
    return "t{}_r{}".format(threads, repeat)


def _locate(root):
    """(results root, platform, design) of the one deployment under `root`.

    Identified by the `base` variant the deployment ships with, which is
    the one directory whose name is known in advance -- as opposed to
    the platform and design, which are what is being discovered.
    """
    hits = []
    for dirpath, dirnames, _ in os.walk(root):
        if os.path.basename(dirpath) != "results":
            continue
        for platform in sorted(dirnames):
            platform_dir = os.path.join(dirpath, platform)
            for design in sorted(os.listdir(platform_dir)):
                if os.path.isdir(os.path.join(platform_dir, design, BASE)):
                    hits.append((dirpath, platform, design))
        dirnames[:] = []
    if not hits:
        raise SystemExit(
            "no results/<platform>/<design>/base under {}: not a deployed "
            "stage reproducer".format(root)
        )
    if len(hits) > 1:
        raise SystemExit(
            "{} deployments under {}: {}".format(
                len(hits), root, ", ".join("/".join(h[1:]) for h in hits)
            )
        )
    return hits[0]
