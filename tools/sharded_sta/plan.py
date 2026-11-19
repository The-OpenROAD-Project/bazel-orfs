"""Which partitions a timing model reads, from the kept-module tree.

A module is named by its name or, as a uniquifying synthesis names a
module after its first instance (`Alu$Top.core.alu`), by the name before
the `$`, which stands for every module of that name.
"""

import json


def load(path):
    with open(path) as f:
        return json.load(f)


def subtree(tree, module):
    out = []
    todo = [module]
    while todo:
        m = todo.pop()
        if m in out:
            continue
        out.append(m)
        todo.extend(tree["modules"][m]["children"])
    return sorted(out)


def resolve(tree, name):
    """The kept modules a listed name stands for."""
    if name in tree["modules"]:
        return [name]
    out = sorted(m for m in tree["modules"] if m.split("$", 1)[0] == name)
    if not out:
        raise ValueError("%s is not a kept module of %s" % (name, tree["top"]))
    return out


def resolve_one(tree, name):
    out = resolve(tree, name)
    if len(out) > 1:
        raise ValueError(
            "%s names %d kept modules (%s); name one" % (name, len(out), ", ".join(out))
        )
    return out[0]


def files(tree, modules):
    return sorted({tree["modules"][m]["file"] for m in modules})
