"""plot ppa for top modules"""

load("@bazel-orfs//:openroad.bzl", "orfs_run")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

def orfs_ppa(name, title, plot, tags = []):
    """Generate PPA plots

    Args:
        name: name of plot target
        title: title of the plot
        plot:
            a list of labels to plot. Names of labels are "Name_<X>_<stage>",
            where X is the x value, stage is e.g. cts and Name is the
            name of the series.
        tags: tags to forward
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
            tags = tags,
        )

    native.filegroup(
        name = "{}_stats".format(name),
        srcs = ["{base}_stats".format(base = base) for base in plot],
        tags = tags,
    )

    native.genrule(
        name = "{}_ppas".format(name),
        srcs = ["{}_stats".format(name)],
        outs = [
            "{}_ppa.pdf".format(name),
            "{}_ppa.yaml".format(name),
            "{}_ppa.csv".format(name),
        ],
        cmd = '$(execpath @bazel-orfs//:plot_clock_period_tool) $(location :{name}_ppa.pdf) $(location :{name}_ppa.yaml) $(location :{name}_ppa.csv) "{title}" $(locations :{name}_stats)'.format(
            name = name,
            title = title,
        ),
        tools = ["@bazel-orfs//:plot_clock_period_tool"],
        tags = tags,
    )
    sh_binary(
        name = name,
        srcs = ["@bazel-orfs//:open_plots.sh"],
        args = ["$(location :{}_ppa.pdf)".format(name)],
        data = [":{}_ppa.pdf".format(name)],
        tags = tags,
    )
