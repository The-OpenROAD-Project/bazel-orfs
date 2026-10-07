"""Regenerate generate_regfile_asap7's goldens in patch 0010.

golden.py <openroad> (from the workspace root, OPENROAD_SRC set): extracts the test's inputs from the patch, runs
the test with <openroad>, and writes its outputs back into the patch as
the new .vok/.defok/.lefok/.libok/.ok.
"""

import os, re, subprocess, sys, shutil

HERE = "tmp/regfile-campaign"
P = "patches/0010-openroad-ram-generate-regfile.patch"
OR = os.environ["OPENROAD_SRC"]  # an OpenROAD checkout: test/helpers.tcl, test/asap7
W = os.path.join(HERE, "golden")
T = "src/ram/test/generate_regfile_asap7"


def hunk(s, path):
    a = s.index("+++ b/%s\n" % path)
    a = s.index("\n", a) + 1
    m = re.match(r"@@ -0,0 \+1,(\d+) @@\n", s[a:])
    n = int(m.group(1))
    b = a + m.end()
    lines = s[b:].split("\n")[:n]
    assert all(l.startswith("+") for l in lines), path
    end = b + sum(len(l) + 1 for l in lines)
    return a, end, [l[1:] for l in lines]


def put(s, path, text):
    a, end, _ = hunk(s, path)
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    new = "@@ -0,0 +1,%d @@\n" % len(lines) + "".join("+" + l + "\n" for l in lines)
    return s[:a] + new + s[end:]


s = open(P).read()
shutil.rmtree(W, ignore_errors=True)
os.makedirs(W)
for ext in (".tcl", ".regfile", "_rtl.v"):
    open(os.path.join(W, os.path.basename(T) + ext), "w").write(
        "\n".join(hunk(s, T + ext)[2]) + "\n"
    )
for ext in ("vok", "defok", "lefok", "libok"):
    open(os.path.join(W, os.path.basename(T) + "." + ext), "w").write("")
shutil.copy(os.path.join(OR, "test/helpers.tcl"), W)
os.symlink(os.path.join(OR, "test/asap7"), os.path.join(W, "asap7"))
r = subprocess.run(
    [sys.argv[1], "-no_init", "-no_splash", "-exit", os.path.basename(T) + ".tcl"],
    cwd=W,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True,
)
log = r.stdout.splitlines()
keep = [
    l
    for l in log
    if l.startswith("[INFO ODB-0227]") or l.startswith("generate_regfile:")
]
assert len(keep) == 3, r.stdout[-2000:]
ok = "\n".join(keep + ["No differences found."] * 4) + "\n"
res = os.path.join(W, "results")
outs = {"vok": "v", "defok": "def", "lefok": "lef", "libok": "lib"}
for g, ext in outs.items():
    f = os.path.join(res, os.path.basename(T) + "-tcl." + ext)
    s = put(s, "%s.%s" % (T, g), open(f).read())
s = put(s, T + ".ok", ok)
# diffstat counts for the regenerated files
for ext in ("defok", "lefok", "libok", "ok", "vok"):
    n = len(hunk(s, "%s.%s" % (T, ext))[2])
    s = re.sub(
        r"(%s\.%s +\| +)\d+ " % (re.escape(T), ext),
        lambda m: m.group(1).rstrip() + " " + str(n) + " ",
        s,
        count=1,
    )
open(P, "w").write(s)
print("\n".join(keep))
