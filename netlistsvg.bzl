"""netlistsvg utility function"""

load("@aspect_rules_js//js:defs.bzl", "js_run_binary")

def netlistsvg(name, src, out):
    """Run netlistsvg on the given source file"""
    js_run_binary(
        name = name,
        srcs = [src],
        outs = [out],
        chdir = native.package_name(),
        # $(location :alu) does not work as the cwd of the nodejs binary is not the
        # workspace root
        args = [src, "-o", out],
        tool = "@bazel-orfs//:netlistsvg",
    )
