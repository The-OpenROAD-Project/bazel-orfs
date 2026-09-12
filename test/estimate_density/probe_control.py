"""Does asking for an estimate change the placement that follows?

`estimate_target_density` resets gpl's Replace object when it is done
(`gpl::replace_reset_cmd`), and every ladder rung calls it before global
placement runs. If that reset left anything behind, every number in this
study would be measuring the probe as much as the design.

The check is two builds of the same rung -- one with the probe attached,
one without, from the same floorplan -- and a byte comparison of the
place stage's ODB. Equal bytes is the strongest statement available; a
difference would mean the ladder measures a perturbed flow and has to say
so.

    python3 test/estimate_density/probe_control.py
"""

import hashlib
import json
import os
import subprocess
import sys

RESULTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "studies",
    "estimate-target-density",
    "results_control",
)

# (name, bazel target). The two differ in the probe and in nothing else:
# both are rung 8 of gcd, both start from ":gcd_base_floorplan".
ARMS = [
    ("with_probe", "//test/estimate_density:gcd_t08_place"),
    ("without_probe", "//test/estimate_density:gcd-noprobe_nt08_place"),
]


def odb_of(target):
    out = subprocess.run(
        ["bazelisk", "cquery", "--output=files", target],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in out.stdout.splitlines():
        if line.strip().endswith("3_place.odb"):
            return line.strip()
    raise RuntimeError("no 3_place.odb among the outputs of " + target)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    os.makedirs(RESULTS, exist_ok=True)
    digests = {}
    for name, target in ARMS:
        subprocess.run(
            ["bazelisk", "build", "--//:log_timestamps", target], check=True
        )
        digests[name] = sha256(odb_of(target))
        print("{:>14}: {}".format(name, digests[name]))

    verdict = {
        "same": digests["with_probe"] == digests["without_probe"],
        "digests": digests,
        "arms": dict(ARMS),
    }
    with open(os.path.join(RESULTS, "probe_control.json"), "w") as handle:
        json.dump(verdict, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("identical" if verdict["same"] else "DIFFERENT -- the probe perturbs the flow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
