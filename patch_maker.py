import sys

patch_content = """--- MODULE.bazel
+++ MODULE.bazel
@@ -14,2 +14,3 @@
 bazel_dep(name = "rules_java", version = "8.14.0")
+bazel_dep(name = "rules_verilog", version = "1.1.1")
 
--- verilog/defs.bzl
+++ verilog/defs.bzl
@@ -4,2 +4,123 @@
 
 verilog_single_file_library = _verilog_single_file_library
+
+load("@rules_verilog//verilog:defs.bzl", "VerilogInfo")
+
+def _fir_library_impl(ctx):
+    fir = ctx.actions.declare_file(ctx.attr.name + ".fir")
+
+    args = ctx.actions.args()
+    args.add_all([ctx.expand_location(opt, ctx.attr.data) for opt in ctx.attr.opts])
+    args.add("-o", fir)
+    ctx.actions.run(
+        arguments = [args],
+        executable = ctx.executable.generator,
+        env = {
+            "CHISEL_FIRTOOL_PATH": ctx.executable._firtool.dirname,
+        },
+        inputs = ctx.attr.generator[DefaultInfo].default_runfiles.files.to_list() +
+                 [ctx.executable._firtool] +
+                 ctx.files.data,
+        outputs = [fir],
+        mnemonic = "FirGeneration",
+    )
+    return [
+        DefaultInfo(
+            runfiles = ctx.runfiles(files = []),
+            files = depset([fir]),
+        ),
+    ]
+
+fir_library = rule(
+    implementation = _fir_library_impl,
+    attrs = {
+        "data": attr.label_list(
+            allow_files = True,
+        ),
+        "generator": attr.label(
+            cfg = "exec",
+            executable = True,
+            mandatory = True,
+        ),
+        "opts": attr.string_list(default = []),
+        "_firtool": attr.label(
+            doc = "Firtool binary.",
+            executable = True,
+            allow_files = True,
+            cfg = "exec",
+            default = Label("@circt//:bin/firtool"),
+        ),
+    },
+)
+
+def _verilog_impl(ctx, split):
+    if split:
+        sv = ctx.actions.declare_directory(ctx.attr.name)
+    else:
+        sv = ctx.actions.declare_file(ctx.attr.name)
+
+    args = ctx.actions.args()
+    args.add("--format=mlir")
+    if split:
+        args.add("--split-verilog")
+
+    args.add_all(ctx.attr.opts)
+    args.add_all(ctx.files.srcs)
+    args.add("-o", sv.path)
+
+    ctx.actions.run(
+        arguments = [args],
+        executable = ctx.executable._firtool,
+        inputs = ctx.files.srcs,
+        outputs = [sv],
+        mnemonic = "VerilogGeneration",
+    )
+
+    verilog_info = VerilogInfo(
+        srcs = depset([sv]),
+        hdrs = depset(),
+        includes = depset([
+            sv.path,
+            sv.path + "/Simulation",
+            sv.path + "/verification",
+            sv.path + "/verification/assume",
+            sv.path + "/verification/cover",
+            sv.path + "/verification/assert",
+        ]),
+        data = depset(),
+        deps = depset(),
+        standard = "",
+        top_module = "",
+    )
+
+    return [
+        DefaultInfo(
+            runfiles = ctx.runfiles(files = []),
+            files = depset([sv]),
+        ),
+        verilog_info,
+    ]
+
+def verilog_attrs():
+    return {
+        "opts": attr.string_list(default = []),
+        "srcs": attr.label_list(
+            doc = "Cell library.",
+            allow_files = True,
+        ),
+        "_firtool": attr.label(
+            doc = "Firtool binary.",
+            executable = True,
+            allow_files = True,
+            cfg = "exec",
+            default = Label("@circt//:bin/firtool"),
+        ),
+    }
+
+verilog_directory = rule(
+    implementation = lambda ctx: _verilog_impl(ctx, split = True),
+    attrs = verilog_attrs(),
+)
+
+verilog_file = rule(
+    implementation = lambda ctx: _verilog_impl(ctx, split = False),
+    attrs = verilog_attrs(),
+)
"""
open("patches/rules_chisel_circt.patch", "w").write(patch_content)
