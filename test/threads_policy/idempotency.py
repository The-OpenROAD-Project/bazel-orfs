#!/usr/bin/env python3
"""Did the thread count change the result -- and is that even the question?

#968's divergence check pooled every arm and every repeat of a
(design, stage, substep) into one set of hashes and reported "more than
one" as a divergence. That answers a runtime study's question, which is
only ever "were the arms comparable". It cannot answer this one, because
it cannot tell apart two findings with different causes and different
fixes:

    run-to-run        the same arm, run twice, disagreed with itself.
                      The thread count is not implicated at all: this
                      is nondeterminism, and it would show up at one
                      thread too.
    thread-dependent  each arm agreed with itself, and a different arm
                      disagreed. This is the class-1/2/3 shape, and the
                      arm where it first appears is the ceiling below
                      which the flow is safe.

Pooling them reports the first as the second, which is how a thread
study talks itself into hunting a thread bug that is not there.

The two are not exclusive, and where both hold the verdict is
`confounded` -- reported as run-to-run, with thread-dependence *not*
claimed on top. A base that disagrees with itself cannot establish that
some other arm disagrees with it; the noise has to be fixed first. This
is deliberately the conservative direction: it under-claims thread bugs
rather than inventing them.

t=1 is the reference, and it is a reference only because it is measured
like any other arm, twice. A golden whose own stability is assumed is
not a golden.

Every verdict is per (design, stage, substep, witness). One witness
diverging and the others holding is itself informative -- a QoR
divergence with an identical ODB is a divergence that was repaired
away, which is the shape in OpenROAD#9781 -- so the witnesses are never
collapsed into one answer.
"""

import collections

import witness

STABLE = "stable"
RUN_TO_RUN = "run-to-run"
THREAD_DEPENDENT = "thread-dependent"
CONFOUNDED = "confounded"
UNPROVEN = "unproven"

# Worst first: this is the order findings are worth reading, and the
# order the report sorts by.
SEVERITY = (CONFOUNDED, THREAD_DEPENDENT, RUN_TO_RUN, UNPROVEN, STABLE)

Key = collections.namedtuple("Key", "design stage step kind")

Verdict = collections.namedtuple(
    "Verdict",
    "key verdict reference first_divergent_arm arms unstable_arms detail",
)


def sample_value(sample, kind):
    """One witness out of one substep sample, or None if unproven."""
    if kind == "qor":
        return sample.get("qor")
    return sample.get(kind + "_sha1")


def comparable(value):
    """A hashable stand-in, so a dict witness can go in a set.

    The QoR witness is a dict. Two dicts with the same items are the
    same witness, so they are compared by their sorted items rather
    than by identity.
    """
    if isinstance(value, dict):
        return tuple(sorted(value.items(), key=lambda kv: kv[0]))
    return value


def index(records):
    """{Key: {threads: {repeat: value}}} over every recorded sample.

    Pinned arms are excluded: `--pin` changes the affinity mask as well
    as the thread count, so a pinned arm and an unpinned one differ in
    two things at once and cannot be each other's reference.
    """
    out = collections.defaultdict(lambda: collections.defaultdict(dict))
    for record in records:
        if record.get("pinned"):
            continue
        for step, sample in (record.get("substeps") or {}).items():
            if not sample.get("ran", True):
                continue
            for kind in witness.KINDS:
                key = Key(record["design"], record["stage"], step, kind)
                out[key][record["threads"]][record["repeat"]] = sample_value(
                    sample, kind
                )
    return out


def classify(arms, reference=1):
    """The verdict for one (design, stage, substep, witness).

    `arms` is {threads: {repeat: value}}.
    """
    unstable = sorted(
        threads
        for threads, repeats in arms.items()
        if len({comparable(v) for v in repeats.values()}) > 1
    )
    unproven = [
        threads
        for threads, repeats in arms.items()
        if any(v is None for v in repeats.values())
    ]

    # An arm's value, where the arm agrees with itself. An arm that
    # does not cannot contribute to a cross-arm comparison.
    settled = {
        threads: comparable(next(iter(repeats.values())))
        for threads, repeats in arms.items()
        if threads not in unstable and repeats
    }

    ref_value = settled.get(reference)
    divergent = sorted(
        threads
        for threads, value in settled.items()
        if threads != reference and ref_value is not None and value != ref_value
    )

    # Arms that could actually be compared against the reference. A
    # ladder of one arm cannot establish invariance no matter how well
    # that arm agrees with itself.
    compared = [t for t in settled if t != reference]

    if unstable and divergent:
        verdict = CONFOUNDED
    elif unstable:
        verdict = RUN_TO_RUN
    elif divergent:
        verdict = THREAD_DEPENDENT
    elif unproven or reference not in arms or ref_value is None or not compared:
        # No divergence found, but nothing was established either: a
        # witness that was never captured, a ladder with no reference
        # arm, or a ladder with nothing but the reference. Silence is
        # not agreement.
        verdict = UNPROVEN
    else:
        verdict = STABLE

    detail = None
    if unproven:
        detail = "witness missing at t={}".format(
            ", ".join(str(t) for t in sorted(unproven))
        )
    elif reference not in arms:
        detail = "no t={} arm, so there is no reference".format(reference)
    elif not compared:
        detail = "only the t={} reference was measured".format(reference)

    return Verdict(
        key=None,
        verdict=verdict,
        reference=ref_value,
        first_divergent_arm=divergent[0] if divergent else None,
        arms=dict(sorted(settled.items())),
        unstable_arms=unstable,
        detail=detail,
    )


def verdicts(records, reference=1):
    """Every verdict, worst first."""
    out = []
    for key, arms in index(records).items():
        got = classify(arms, reference)
        out.append(got._replace(key=key))
    return sorted(
        out,
        key=lambda v: (
            SEVERITY.index(v.verdict),
            v.key.design,
            v.key.stage,
            v.key.step,
            witness.KINDS.index(v.key.kind),
        ),
    )


def safe_ceiling(all_verdicts):
    """The highest thread count nothing diverged at, per design+stage.

    The number a policy needs. Only thread-dependent verdicts set it: a
    run-to-run finding says nothing about which thread count is safe,
    because no thread count is.
    """
    out = {}
    for got in all_verdicts:
        if got.verdict != THREAD_DEPENDENT or not got.first_divergent_arm:
            continue
        pair = (got.key.design, got.key.stage)
        below = [t for t in got.arms if t < got.first_divergent_arm]
        ceiling = max(below) if below else None
        if pair not in out or (ceiling is not None and out[pair] > ceiling):
            out[pair] = ceiling
    return out


def thread_blind(records):
    """(design, stage, step) that used one core's worth of CPU.

    A substep that never went parallel measures nothing about thread
    policy, so a divergence there cannot be blamed on threads -- it is
    a nondeterminism finding wearing a thread study's clothes. #968's
    threshold, reused: cpu% at or below 110.
    """
    peak = collections.defaultdict(int)
    for record in records:
        for step, sample in (record.get("substeps") or {}).items():
            cpu = sample.get("cpu_pct")
            if cpu is None:
                continue
            triple = (record["design"], record["stage"], step)
            peak[triple] = max(peak[triple], cpu)
    return {triple for triple, cpu in peak.items() if cpu <= 110}


def counts(all_verdicts):
    return collections.Counter(v.verdict for v in all_verdicts)
