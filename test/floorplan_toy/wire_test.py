"""The wire model's repeated ps/um on the pin layers (pdk.json) against
the routed parent's: the median over spans of 100 um and more of the
wire's own delay per micron (probe_wire.tcl) is within the 50 % error
bars of the model, which also charges the repeater."""

import json
import sys
import unittest

ARGS = []


class WireTest(unittest.TestCase):
    def test_routed_ps_per_um(self):
        wire, pdk_path = ARGS
        spans = []
        with open(wire) as f:
            for line in f:
                um, ps, per_um, _ = line.split()
                if float(um) >= 100.0:
                    spans.append(float(per_um))
        self.assertGreater(len(spans), 10)
        spans.sort()
        median = spans[len(spans) // 2]
        with open(pdk_path) as f:
            pdk = json.load(f)
        model = max(
            pdk["layers"][n]["ps_per_um"] for n in pdk["io"]["H"] + pdk["io"]["V"]
        )
        print(
            "routed median %.3f ps/um over %d spans, model %.3f"
            % (median, len(spans), model)
        )
        self.assertAlmostEqual(median, model, delta=0.5 * model)


if __name__ == "__main__":
    ARGS = sys.argv[1:]
    unittest.main(argv=sys.argv[:1])
