"""The §4.8 cross-check table, from stage_power() outputs."""

def synth_crosscheck(name, arms, periods_ps, per_mhz, tags = ["manual"], visibility = None):
    """Render core-only energy per CoreMark iteration for several arms.

    Args:
      name: target name; the table is `<name>.md`, the data `<name>.json`.
      arms: {label: stage_power() target}. Its `_vector_driven.json` is read.
      periods_ps: {label: SDC clock period in ps} for the same labels.
      per_mhz: the *_per_mhz.json, for cycles per iteration.
      tags: forwarded; manual.
      visibility: forwarded.
    """
    srcs = [per_mhz]
    args = ["--per-mhz $(location {})".format(per_mhz)]
    for label, target in arms.items():
        power = target + "_vector_driven.json"
        srcs.append(power)
        args.append("--arm '{}:{}:$(location {})'".format(label, periods_ps[label], power))
    native.genrule(
        name = name,
        srcs = srcs,
        outs = [name + ".md", name + ".json"],
        cmd = " ".join(
            ["$(execpath //test/coremark_joule/scripts:synth_crosscheck)"] + args + [
                "--out-md $(location {}.md)".format(name),
                "--out-json $(location {}.json)".format(name),
            ],
        ),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:synth_crosscheck"],
        visibility = visibility,
    )
