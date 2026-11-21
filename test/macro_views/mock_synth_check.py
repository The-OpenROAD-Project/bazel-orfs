"""Top's netlist, synthesised against Block's ports-only view, keeps Block
as two blackbox instances, every port connected."""

import re
import sys

text = open(sys.argv[1]).read()
assert not re.search(
    r"^\s*module\s+Block\b", text, re.M
), "Block was synthesised into Top"
instances = re.findall(r"^\s*Block\s+\\?(\S+)\s*\((.*?)\);", text, re.M | re.S)
assert len(instances) == 2, "expected two Block instances, found %d" % len(instances)
for name, body in instances:
    ports = set(re.findall(r"\.(\w+)\s*\(", body))
    assert ports == {"clock", "in_bits", "in_valid", "out_bits", "out_valid"}, (
        name,
        ports,
    )
print("ok")
