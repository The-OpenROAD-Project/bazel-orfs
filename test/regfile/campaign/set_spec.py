"""set_spec.py <bit_folds> <utilisation|->: set riscv32i-regfile's
bit_folds, and a CORE_UTILIZATION override or none (riscv32i's 62 %), in
patches/0089 in place. Run from the workspace root."""

import re, sys

P = "patches/0089-orfs-auto-memories-regfiles.patch"
s = open(P).read()
folds, util = sys.argv[1], sys.argv[2]
s, n = re.subn(r"\n\+bit_folds \d+\n", "\n+bit_folds %s\n" % folds, s)
assert n == 1
s = re.sub(r"\+export CORE_UTILIZATION = \d+\n\+\n", "", s)
inc = "+include designs/asap7/riscv32i/config.mk\n+\n"
assert s.count(inc) == 1
if util != "-":
    s = s.replace(inc, inc + "+export CORE_UTILIZATION = %s\n+\n" % util)
a = s.index("+++ b/flow/designs/asap7/riscv32i-regfile/config.mk\n")
h = s.index("@@", a)
e = s.index("\n", h) + 1
nxt = s.index("\ndiff --git", e)
n = sum(1 for l in s[e : nxt + 1].splitlines() if l.startswith("+"))
s = s[:h] + "@@ -0,0 +1,%d @@\n" % n + s[e:]
open(P, "w").write(s)
