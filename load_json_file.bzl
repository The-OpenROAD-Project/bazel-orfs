"""
A repository rule to load a yaml file and convert it into a Starlark file.

Downloads yq to perform the YAML-to-JSON conversion, avoiding any
dependency on a locally installed Python or pyyaml.
"""

_YQ_VERSION = "4.52.4"

_YQ_SHA256 = {
    "linux_amd64": "0c4d965ea944b64b8fddaf7f27779ee3034e5693263786506ccd1c120f184e8c",
    "linux_arm64": "4c2cc022a129be5cc1187959bb4b09bebc7fb543c5837b93001c68f97ce39a5d",
    "darwin_amd64": "d72a75fe9953c707d395f653d90095b133675ddd61aa738e1ac9a73c6c05e8be",
    "darwin_arm64": "6bfa43a439936644d63c70308832390c8838290d064970eaada216219c218a13",
}

def _load_json_file_impl(repository_ctx):
    os_name = repository_ctx.os.name
    if "linux" in os_name:
        yq_os = "linux"
    elif "mac" in os_name:
        yq_os = "darwin"
    else:
        fail("Unsupported OS for yq download: {}".format(os_name))

    arch = repository_ctx.os.arch
    if arch == "amd64" or arch == "x86_64":
        yq_arch = "amd64"
    elif arch == "aarch64" or arch == "arm64":
        yq_arch = "arm64"
    else:
        fail("Unsupported architecture for yq download: {}".format(arch))

    platform_key = "{}_{}".format(yq_os, yq_arch)
    sha256 = _YQ_SHA256.get(platform_key)
    if not sha256:
        fail("No yq SHA256 for platform: {}".format(platform_key))

    repository_ctx.download(
        url = "https://github.com/mikefarah/yq/releases/download/v{}/yq_{}_{}".format(
            _YQ_VERSION,
            yq_os,
            yq_arch,
        ),
        output = "yq",
        executable = True,
        sha256 = sha256,
    )

    yaml_file = repository_ctx.path(repository_ctx.attr.src)
    result = repository_ctx.execute(["./yq", "-o", "json", ".", str(yaml_file)])
    if result.return_code != 0:
        fail("Failed to convert yaml to json: {}".format(result.stderr))

    json_data = json.decode(result.stdout)

    # Strip "description" fields to reduce size
    cleaned = {
        k: {field: val for field, val in v.items() if field != "description"}
        for k, v in json_data.items()
    }

    repository_ctx.file("json.bzl", "orfs_variable_metadata = " + repr(cleaned))
    repository_ctx.file("BUILD", "")

load_json_file = repository_rule(
    implementation = _load_json_file_impl,
    attrs = {
        "src": attr.label(allow_single_file = True),
    },
    local = True,
)
