"""plot ppa for top modules"""

load("@bazel-orfs//:openroad.bzl", "orfs_run")

def orfs_ppa(name, title, plot):
    """Generate PPA plots

    Args:
        name: name of plot target
        title: title of the plot
        plot:
            a list of labels to plot. Names of labels are "Name_<X>_<stage>",
            where X is the x value, stage is e.g. cts and Name is the
            name of the series.
    """
    for base in plot:
        orfs_run(
            name = "{base}_power".format(base = base),
            src = "{base}".format(base = base),
            outs = [
                "{base}_stats".format(base = base),
            ],
            arguments = {
                "OUTPUT": "$(location :{base}_stats)".format(base = base),
            },
            script = "@bazel-orfs//:power.tcl",
        )

    native.filegroup(
        name = "{}_stats".format(name),
        srcs = ["{base}_stats".format(base = base) for base in plot],
    )

    native.genrule(
        name = "{}_ppas".format(name),
        srcs = ["{}_stats".format(name)],
        outs = ["{}_ppa.pdf".format(name)],
        cmd = "$(execpath @bazel-orfs//:plot_clock_period_tool) $@ \"{title}\" $(locations :{name}_stats)".format(name = name, title = title),
        tools = ["@bazel-orfs//:plot_clock_period_tool"],
    )

    native.sh_binary(
        name = name,
        srcs = ["open_plots.sh"],
        args = ["$(location :{}_ppas)".format(name)],
        data = ["{}_ppas".format(name)],
    )
