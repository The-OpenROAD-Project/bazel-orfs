#! /bin/env python3

import argparse
import hashlib
import os
import shutil
import subprocess
import tarfile
import tempfile
import typing
import urllib.parse


class Label(typing.NamedTuple):
    repo: str
    package: str
    name: str


def label(s):
    (repo, path) = s.split("//")
    (package, name) = path.split(":")
    return Label(repo=repo, package=package, name=name)


class File(typing.NamedTuple):
    path: str
    root: str
    workspace_root: str

    def runfile_path(self):
        return os.path.join(
            os.environ["RUNFILES"], os.path.relpath(self.path, self.root)
        )

    def archive_path(self):
        return os.path.relpath(
            os.path.relpath(self.path, self.root), self.workspace_root
        )


def file(s):
    (path, root, workspace_root) = s.split("@")
    return File(path=path, root=root, workspace_root=workspace_root)


class Artifact(typing.NamedTuple):
    label: Label
    files: typing.Set[File]


class ArtifactAction(argparse.Action):

    def __init__(self, option_strings, dest, nargs, **kwargs):
        super().__init__(option_strings, dest, nargs, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        artifacts = []
        for artifact in values:
            (l, root, files) = artifact.split(",")
            artifacts.append(
                Artifact(
                    label=label(l), files=frozenset([file(s) for s in files.split(":")])
                )
            )
        setattr(namespace, self.dest, artifacts)


def build_write(artifacts, output):
    for artifact in artifacts:
        match sorted(artifact.files):
            case [x] if (
                os.path.relpath(x.archive_path(), artifact.label.package)
                == artifact.label.name
            ):
                print("exports_files(", file=output)
                print("  srcs = [", file=output)
                for file in artifact.files:
                    print(
                        "    {},".format(
                            repr(
                                os.path.relpath(
                                    file.archive_path(), artifact.label.package
                                )
                            )
                        ),
                        file=output,
                    )
                print("  ],".format(artifact.label), file=output)
                print('  visibility = ["//visibility:public"],', file=output)
                print(")", file=output)
            case _:
                print("filegroup(", file=output)
                print("  name = {},".format(repr(artifact.label.name)), file=output)
                print("  srcs = [", file=output)
                for file in sorted(artifact.files):
                    print(
                        "    {},".format(
                            repr(
                                os.path.relpath(
                                    file.archive_path(), artifact.label.package
                                )
                            )
                        ),
                        file=output,
                    )
                print("  ],".format(artifact.label), file=output)
                print('  visibility = ["//visibility:public"],', file=output)
                print(")", file=output)


def gs(bucket, path):
    return urllib.parse.urlunparse(("gs", bucket, path, None, None, None))


def https(bucket, path):
    return urllib.parse.urlunparse(
        (
            "https",
            "storage.googleapis.com",
            os.path.join(bucket, path),
            None,
            None,
            None,
        )
    )


def reset(tarinfo):
    tarinfo.mtime = 0
    tarinfo.uid = 0
    tarinfo.uname = "root"
    tarinfo.gid = 0
    tarinfo.gname = "root"
    return tarinfo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--bucket", help="Google cloud bucket used for uploads.")
    parser.add_argument("-l", "--lock", help="Lock file.")
    parser.add_argument("-p", "--package", help="Bazel package.")
    parser.add_argument("artifact", action=ArtifactAction, nargs="+")

    args = parser.parse_args()

    pkgs = {}
    for artifact in args.artifact:
        pkgs.setdefault(artifact.label.package, []).append(artifact)

    path = tempfile.mkdtemp()
    try:
        tar_path = os.path.join(path, args.lock + ".tar")
        with tarfile.open(tar_path, "w", dereference=True) as tar:
            for pkg, artifacts in pkgs.items():
                pkg_build_path = os.path.join(pkg, "BUILD")
                build_path = os.path.join(path, pkg_build_path)
                os.makedirs(os.path.dirname(build_path), exist_ok=True)

                with open(build_path, "w") as build:
                    build_write(artifacts, build)

                tar.add(build_path, arcname=pkg_build_path, filter=reset)
                for file in sorted(
                    frozenset.union(*[artifact.files for artifact in artifacts])
                ):
                    tar.add(
                        file.runfile_path(), arcname=file.archive_path(), filter=reset
                    )

        with open(tar_path, "rb") as f:
            sha256 = hashlib.file_digest(f, "sha256")

        dir, _ = os.path.splitext(args.lock)
        name = os.path.join(args.package, dir, sha256.hexdigest() + ".tar")
        subprocess.run(["gsutil", "mv", "-n", "-Z", tar_path, gs(args.bucket, name)])

        with open(
            os.path.join(
                os.environ["BUILD_WORKSPACE_DIRECTORY"], args.package, args.lock
            ),
            "w",
        ) as f:
            f.write(https(args.bucket, name))
            f.write("@")
            f.write(sha256.hexdigest())

    finally:
        shutil.rmtree(path)


if __name__ == "__main__":
    main()
