"""Rules for sby"""

load("//:generate.bzl", "fir_library")
load("//:verilog.bzl", "verilog_directory", "verilog_single_file_library")

def _sby_test_impl(ctx):
    sby = ctx.actions.declare_file(ctx.attr.name + ".sby")

    ctx.actions.expand_template(
        template = ctx.file._sby_template,
        output = sby,
        substitutions = {
            "${VERILOG}": "\n".join(
                [file.short_path for file in ctx.files.verilog_files],
            ),
            "${TOP}": ctx.attr.module_top,
        },
    )

    script = ctx.actions.declare_file(ctx.attr.name + ".run.sh")
    ctx.actions.write(
        script,
        content = """
#!/bin/sh
set -xeuo pipefail
test_status=0
find .
VERILOG_BASE_NAMES="{VERILOG_BASE_NAMES}"
# $VERILOG_BASE_NAMES is a list of verilog files and folders
# that contain .sv and .v files. Generate a list of the verilog
# files for yosys to read.

#find $VERILOG_BASE_NAMES
#find $VERILOG_BASE_NAMES -regex ".*sv\\$"
#find $VERILOG_BASE_NAMES -regex ".*\\.\\(v\\|sv\\)$"
find $VERILOG_BASE_NAMES -regex ".*\\.\\(v\\|sv\\)$"
echo blah
VERILOG_FILES=$(find $VERILOG_BASE_NAMES -regex ".*\\.\\(v\\|sv\\)$" | xargs echo)
# replace multiline error/fatail with assert(0);
# Example:

# remove these lines:

#sed -i '/\\else $error/d' $VERILOG_FILES

# replace these lines:
# with just ";"
sed -i -E 's/else \\$(error|fatal)([^;]*);/;/g' $VERILOG_FILES

#sed -i '/\\$fwrite/d' $VERILOG_FILES
#sed -i '/\\$fopen/d' $VERILOG_FILES
#sed -i '/\\$fclose/d' $VERILOG_FILES

VERILOG_FOLDERS=$(find $VERILOG_BASE_NAMES -type d | xargs echo)
# Strip $(dirname $TEST_BINARY) prefix from VERILOG_FILES to get
# the right path.
VERILOG_FILES=$(echo $VERILOG_FILES | sed "s|$(dirname $TEST_BINARY)/||g")
# Next we need to add all the -I for each of the folders in VERILOG_FOLDERS
for folder in $VERILOG_FOLDERS; do
    # Strip $(dirname $TEST_BINARY) prefix from folder to get
    # the right path.
    folder=$(echo $folder | sed "s|$(dirname $TEST_BINARY)/||g")
    VERILOG_FILES="-I $folder $VERILOG_FILES"
done
# Now we use sed to replace VERILOG_BASE_NAMES with VERILOG_FILES
# in the yosys script.
sed -i "s|VERILOG_BASE_NAMES|$VERILOG_FILES|g" {sby_script}
cat {sby_script}
(exec {sby} "$@" {sby_script}) || test_status=$?
test_status=1
if [ $test_status -ne 0 ]; then
    echo "Copying $(find . | wc -l) files to bazel-testlogs/$(dirname $TEST_BINARY)/test.outputs for inspection."
    cp -r $(dirname $TEST_BINARY)/* "$TEST_UNDECLARED_OUTPUTS_DIR/"
    exit $test_status
fi
""".format(
            sby = ctx.executable._sby.short_path,
            sby_script = sby.short_path,
            VERILOG_BASE_NAMES = " ".join(
                [file.short_path for file in ctx.files.verilog_files],
            ),
        ),
        is_executable = True,
    )

    return [
        DefaultInfo(
            files = depset([script]),
            executable = script,
            runfiles = ctx.runfiles(
                files = [sby, ctx.executable._sby, ctx.executable._yosys] +
                        ctx.files.verilog_files,
                transitive_files = depset(
                    transitive = [
                        ctx.attr._sby[DefaultInfo].default_runfiles.files,
                        ctx.attr._sby[DefaultInfo].default_runfiles.symlinks,
                        ctx.attr._yosys[DefaultInfo].default_runfiles.files,
                        ctx.attr._yosys[DefaultInfo].default_runfiles.symlinks,
                    ],
                ),
            ),
        ),
    ]

_sby_test = rule(
    implementation = _sby_test_impl,
    attrs = {
        "verilog_files": attr.label_list(
            allow_files = True,
            providers = [DefaultInfo],
        ),
        "module_top": attr.string(mandatory = True),
        "_sby": attr.label(
            doc = "sby binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@oss_cad_suite//:sby"),
        ),
        "_yosys": attr.label(
            doc = "Yosys binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@oss_cad_suite//:yosys"),
        ),
        "_sby_template": attr.label(
            default = "sby.tpl",
            allow_single_file = True,
        ),
    },
    test = True,
)

def sby_test(
        name,
        module_top,
        generator,
        generator_opts = [],
        verilog_files = [],
        **kwargs):
    """sby_test macro frontend to run formal verification with sby.

    Args:
        name: Name of the test target.
        module_top: Top module name in the verilog files.
        generator: Label of the scala binary that generates the verilog files.
        generator_opts: List of options passed to Generator scala app for generating the verilog.
        verilog_files: List of additional verilog files to include in the sby test.
        **kwargs: Additional args passed to _sby_test.
    """

    # massage output for sby
    firtool_options = [
        #"--help",
       "--disable-all-randomization",
        "-strip-debug-info",
        "--default-layer-specialization=enable",
        "--verification-flavor=immediate",
        #"-disable-layers=Verification",
        #"-disable-layers=Verification.Assert",
        #"-disable-layers=Verification.Assume",
        #"-disable-layers=Verification.Cover",
        "--lowering-options=disallowPackedArrays,disallowLocalVariables,noAlwaysComb,verifLabels",
    ]

    fir_library(
        name = "{name}_fir".format(name = name),
        data = [],
        generator = generator,
        opts = generator_opts + firtool_options,
        tags = ["manual"],
    )

    # FIXME we have to split the files or we get the verification layer stubs
    # https://github.com/llvm/circt/issues/9020
    verilog_directory(
        name = "{name}_split".format(name = name),
        srcs = [":{name}_fir".format(name = name)],
        opts = firtool_options,
        tags = ["manual"],
    )

    # And concat the files into one again for sby
    verilog_single_file_library(
        name = "{name}.sv".format(name = name),
        srcs = [":{name}_split".format(name = name)],
        tags = ["manual"],
        visibility = ["//visibility:public"],
    )

    _sby_test(
        name = name + "_test",
        module_top = module_top,
        verilog_files = verilog_files + [":{name}_split".format(name = name)],
        **kwargs
    )
