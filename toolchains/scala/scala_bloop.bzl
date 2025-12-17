"""Output bloop configurations"""

load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load(
    "//toolchains/scala/impl:aspects.bzl",
    "SemanticDbInfo",
    "scala_diagnostics_aspect",
)

def _scala_bloop_impl(ctx):
    directory = "__EXEC_ROOT__"

    outs = []
    source_jars = []
    top = ctx.attr.src
    for target in [top] + top[SemanticDbInfo].deps.to_list():
        name = target.label.name
        info = target[SemanticDbInfo]

        if len(info.srcs.to_list()) == 0:
            continue

        # Follows schema at https://scalacenter.github.io/bloop/docs/assets/bloop-schema.json
        content = struct(
            version = "1.0.0",
            project = struct(
                name = name,
                directory = directory,
                sources = ["/".join([directory, f.path]) for f in info.srcs.to_list()],
                dependencies = [],  # [d.label.name for d in info.deps.to_list()],
                classpath = ["/".join([directory, f.path]) for f in info.jars.to_list()],
                out = "/".join([directory, ctx.attr.directory, "out", name]),
                classesDir = "/".join(
                    [directory, ctx.attr.directory, "out", name, "classes"],
                ),
                resources = [],
                scala = struct(
                    organization = "org.scala-lang",
                    name = "scala-compiler",
                    version = "2.13.18",
                    options = info.scalacopts.to_list(),
                    jars = [
                        "/".join([directory, f.path])
                        for f in info.compiler[JavaInfo].compilation_info.runtime_classpath.to_list()
                    ],
                ),
                java = struct(
                    options = [],
                ),
                resolution = struct(
                    modules = [
                        struct(
                            name = d.label.name,
                            organization = "TODO",
                            version = "TODO",
                            artifacts = [
                                            struct(
                                                name = d.label.name,
                                                path = "/".join([directory, j.path]),
                                            )
                                            for j in d[JavaInfo].compile_jars.to_list()
                                        ] +
                                        [
                                            struct(
                                                name = d.label.name,
                                                classifier = "sources",
                                                path = "/".join([directory, j.path]),
                                            )
                                            for j in d[JavaInfo].source_jars
                                        ],
                        )
                        for d in info.deps.to_list()
                    ],
                ),
            ),
        )
        out = ctx.actions.declare_file(name + ".json")
        ctx.actions.write(output = out, content = json.encode_indent(content))
        outs.append(out)
        source_jars.append(
            depset(
                [j for d in info.deps.to_list() for j in d[JavaInfo].source_jars],
                transitive = [
                    info.compiler.default_runfiles.files,
                    info.jars,
                ],
            ),
        )

    all_jars = depset(transitive = source_jars)

    manifest = ctx.actions.declare_file(ctx.label.name + ".manifest.json")
    ctx.actions.write(
        output = manifest,
        content = json.encode_indent(
            set(
                [
                    f.owner.workspace_root
                    for f in all_jars.to_list()
                    if f.owner.workspace_root
                ],
            ),
        ),
    )
    args = ctx.actions.args()
    args.add("--directory", ctx.attr.directory)
    args.add("--manifest", manifest.short_path)
    args.add("--check-bloop")
    args.add_all([f.short_path for f in outs])

    ctx.actions.write(
        output = ctx.outputs.parameters,
        content = args,
    )

    link = ctx.actions.declare_file(ctx.label.name + ".exe")
    ctx.actions.symlink(
        output = link,
        target_file = ctx.executable._deploy,
        is_executable = True,
    )

    return [
        DefaultInfo(
            executable = link,
            runfiles = ctx.runfiles(
                [link, manifest, ctx.outputs.parameters] + outs,
                transitive_files = depset(
                    transitive = [
                        all_jars,
                        ctx.attr._deploy[DefaultInfo].default_runfiles.files,
                        ctx.attr._deploy[DefaultInfo].default_runfiles.symlinks,
                    ],
                ),
            ),
            files = depset(outs),
        ),
    ]

_scala_bloop = rule(
    implementation = _scala_bloop_impl,
    attrs = {
        "directory": attr.string(
            doc = "Directory to deploy configuration files to.",
            default = ".bloop",
        ),
        "parameters": attr.output(
            doc = "Name of the file containing deployment parameters.",
        ),
        "src": attr.label(
            aspects = [scala_diagnostics_aspect],
            allow_files = True,
            mandatory = True,
        ),
        "_deploy": attr.label(
            doc = "Compilation database deployment binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("//tools:deploy"),
        ),
    },
    executable = True,
    provides = [
        DefaultInfo,
    ],
    toolchains = [
        "//toolchains/scala:toolchain_type",
    ],
)

def scala_bloop(**kwargs):
    parameters = kwargs.setdefault("parameters", kwargs.get("name") + ".params")
    _scala_bloop(
        args = [
            "@$(location {})".format(parameters),
        ],
        **kwargs
    )
