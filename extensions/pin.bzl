"""Pinning of artifacts"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

def _attrs(content):
    (url, sha256) = content.split("@")
    return {
        "sha256": sha256,
        "url": url,
    }

def _pin_impl(repository_ctx):
    for mod in repository_ctx.modules:
        for install in mod.tags.artifacts:
            content = repository_ctx.read(install.artifacts_lock)
            http_archive(name = install.repo_name, **_attrs(content))

pin = module_extension(
    implementation = _pin_impl,
    tag_classes = {
        "artifacts": tag_class(
            attrs = {
                "artifacts_lock": attr.label(),
                "repo_name": attr.string(),
            },
        ),
    },
)
