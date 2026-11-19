"""Which partitions a timing model or a shard reads, from the kept-module tree.

A shard lists kept modules, each by its name or, as a uniquifying
synthesis names a module after its first instance (`Alu$Top.core.alu`),
by the name before the `$`, which then lists every module of that name.

An instance belongs to the shard that lists its module or, when that is
not listed, to the shard of its nearest listed ancestor; instances with
no listed ancestor belong to the glue shard. A module kept in two places
can belong to two shards, one per place. A shard reads the modules along
the chains it owns as netlists (an ancestor too: a liberty cell cannot
hold an instance), and every other subtree as the timing model of the
subtree's root. It reports only the endpoints of the instances it owns,
so every endpoint is reported by exactly one shard.
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


def check_shards(tree, shards, glue):
    listed = {}
    for shard, names in sorted(shards.items()):
        for name in names:
            for m in resolve(tree, name):
                if m in listed:
                    raise ValueError(
                        "%s is listed by both shard %s and shard %s"
                        % (m, listed[m], shard)
                    )
                listed[m] = shard
    if glue in shards and shards[glue]:
        raise ValueError(
            "the glue shard %s lists modules; it owns what no shard lists" % glue
        )
    return listed


def paths(tree):
    """Every chain of kept modules from the top down, as tuples."""
    out = []
    todo = [(tree["top"],)]
    while todo:
        p = todo.pop()
        out.append(p)
        todo.extend(p + (c,) for c in tree["modules"][p[-1]]["children"])
    return sorted(out)


def owners(tree, shards, glue):
    """{module chain: shard}: the shard listing the chain's last listed
    module, or the glue shard. Every instance of a module sits at the end
    of one chain, so a module kept under two shards' modules has one owner
    per place it sits."""
    listed = check_shards(tree, shards, glue)
    out = {}
    for p in paths(tree):
        owner = glue
        for m in p:
            owner = listed.get(m, owner)
        out[p] = owner
    return out


def shard_plan(tree, shards, glue, shard):
    """(netlist modules, modelled modules, modules listed here, modules
    listed by the other shards) of one shard. The netlists are every
    module along the chains the shard owns: those chains' ends and their
    ancestors."""
    listed = check_shards(tree, shards, glue)
    netlist = set()
    for p, owner in owners(tree, shards, glue).items():
        if owner == shard:
            netlist |= set(p)
    models = set()
    for m in netlist:
        for c in tree["modules"][m]["children"]:
            if c not in netlist:
                models.add(c)
    here = sorted(m for m, s in listed.items() if s == shard)
    elsewhere = sorted(m for m, s in listed.items() if s != shard)
    return sorted(netlist), sorted(models), here, elsewhere


def files(tree, modules):
    return sorted({tree["modules"][m]["file"] for m in modules})
