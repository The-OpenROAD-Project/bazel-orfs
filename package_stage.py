"""Create a .tar.gz from a manifest of src_path\tdst_path lines.

With a third argument, the odb_codec: each .odb it reformatted goes into
the archive as OpenROAD wrote it, so that any openroad opens it.
"""

import os
import subprocess
import sys
import tarfile
import tempfile

MAGIC = b"ODBCODEC"


def is_encoded(path):
    with open(path, "rb") as f:
        return f.read(len(MAGIC)) == MAGIC


def main():
    manifest_path = sys.argv[1]
    output_path = sys.argv[2]
    codec = sys.argv[3] if len(sys.argv) > 3 else None

    with tempfile.TemporaryDirectory() as scratch:
        with tarfile.open(output_path, "w:gz") as tar:
            seen = set()
            with open(manifest_path) as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    src, dst = line.split("\t", 1)
                    if dst in seen:
                        continue
                    seen.add(dst)
                    if codec and src.endswith(".odb") and is_encoded(src):
                        decoded = os.path.join(scratch, "decoded.odb")
                        with open(decoded, "wb") as out:
                            subprocess.run(
                                [codec, "decode", src], stdout=out, check=True
                            )
                        tar.add(decoded, arcname=dst)
                        os.remove(decoded)
                    else:
                        tar.add(src, arcname=dst)


if __name__ == "__main__":
    main()
