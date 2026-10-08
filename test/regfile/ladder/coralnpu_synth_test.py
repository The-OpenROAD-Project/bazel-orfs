"""asap7/coralnpu's synthesis is the build its config says it is.

Reads the synthesized netlist (1_2_yosys.v) and AUTO_MEMORIES' inventory
(memories.json) of @orfs//flow/designs/asap7/coralnpu and checks what
ORFS patch 0102 (upstream as ORFS #4653) sets out to do:

- firtool's verification layers are gone: no *_Verification_* module;
- each module of SYNTH_KEEP_MODULES is a module of its own, and only
  those besides the top and the generated SRAM views;
- both TCM SRAMs are generated macros with one read-write port and
  their 16-lane byte mask.
"""

import json
import os
import re
import sys
import unittest

KEEP = [
    "SCore",
    "UncachedFetch",
    "DispatchV1",
    "Regfile",
    "FRegfile",
    "LsuV1",
    "Csr",
    "FloatCore",
    "AxiSlave",
    "DBus2AxiV1",
]


def find(suffix):
    found = [p for p in sys.argv[1:] if p.endswith(suffix)]
    if len(found) != 1:
        raise SystemExit(
            "expected one %s among %s"
            % (suffix, [os.path.basename(p) for p in sys.argv[1:]])
        )
    return found[0]


class CoralnpuSynthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(find("/1_2_yosys.v")) as f:
            cls.netlist = f.read()
        with open(find("/memories.json")) as f:
            cls.memories = json.load(f)
        cls.modules = re.findall(r"^module\s+(\S+?)\s*\(", cls.netlist, re.M)

    def test_no_verification_layers(self):
        self.assertNotIn("_Verification_", self.netlist)

    def test_kept_modules(self):
        defs = {m.lstrip("\\").split("$")[0] for m in self.modules}
        for k in KEEP:
            self.assertIn(k, defs)
        self.assertIn("CoreMiniAxi", defs)
        extra = {
            d for d in defs - set(KEEP) - {"CoreMiniAxi"} if not d.startswith("Sram_")
        }
        self.assertEqual(sorted(extra), [])

    def test_srams_are_masked_macros(self):
        mems = {m["name"]: m for m in self.memories["memories"]}
        for depth in (512, 2048):
            m = mems["Sram_%dx128_mem" % depth]
            self.assertTrue(m["idiomatic"], m.get("reason"))
            self.assertEqual(m["rows"], depth)
            self.assertEqual(m["bits"], 128)
            self.assertEqual(m["mask_lanes"], 16)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
