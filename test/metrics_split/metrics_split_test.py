"""A <stage>_report reproduces the stage's in-stage report_metrics.

Each argument is `stage=instage.json,instage.rpt,report.json,report.rpt`,
instage.rpt empty where the stage declares none. The in-stage files come
from a flow built with SKIP_REPORT_METRICS=0, the report's from the same flow built
with bazel-orfs's default SKIP_REPORT_METRICS=1 and reported on its saved
results. Every metric the report writes must be in the in-stage .json
with the same value, and the two .rpt files must be the same text.
"""

import json
import sys
import unittest

# Every stage's report must have measured these, not only area: a report
# that ran on an empty design or skipped STA would pass the comparison.
REQUIRED = ("timing__setup__ws", "timing__hold__ws", "power__total")

# Written by OpenROAD's logger, not by report_metrics: the counts of the
# report process's own messages.
LOGGER_PREFIX = "flow__"


def load(path):
    """Every value each key has in the file, in order.

    OpenROAD's logger writes a key once per call: a stage that legalises
    twice writes its dpl counters twice.
    """
    values = {}

    def pairs_hook(pairs):
        for k, v in pairs:
            values.setdefault(k, []).append(v)
        return {}

    with open(path) as f:
        json.load(f, object_pairs_hook=pairs_hook)
    return values


def one_value(path, values, key):
    distinct = []
    for v in values[key]:
        if v not in distinct:
            distinct.append(v)
    if len(distinct) != 1:
        raise ValueError("{}: {} has values {}".format(path, key, distinct))
    return distinct[0]


def last_value(values, key):
    """The value a json reader gets: the last one written.

    At finish, report_cell_usage (OpenROAD's dbSta) writes
    design__instance__area/count with the fill cells, before
    report_metrics writes them without; the report process runs only
    report_metrics.
    """
    return values[key][-1]


def parse_args(argv):
    cases = {}
    for arg in argv:
        stage, files = arg.split("=", 1)
        cases[stage] = tuple(files.split(","))
    return cases


class MetricsSplitTest(unittest.TestCase):
    cases = {}

    def test_stages(self):
        self.assertEqual(sorted(self.cases), ["cts", "final", "grt", "place"])
        for stage, (instage_json, instage_rpt, report_json, report_rpt) in sorted(
            self.cases.items()
        ):
            with self.subTest(stage=stage):
                instage = load(instage_json)
                report_values = load(report_json)
                report = {
                    k: one_value(report_json, report_values, k)
                    for k in report_values
                    if not k.startswith(LOGGER_PREFIX)
                }
                for suffix in REQUIRED:
                    self.assertTrue(
                        any(k.endswith("__" + suffix) for k in report),
                        "{}: no *__{} in {}".format(stage, suffix, sorted(report)),
                    )
                missing = sorted(set(report) - set(instage))
                self.assertEqual(
                    missing, [], "{}: not in the in-stage .json".format(stage)
                )
                differ = {
                    k: (last_value(instage, k), report[k])
                    for k in sorted(report)
                    if last_value(instage, k) != report[k]
                }
                self.assertEqual(differ, {}, "{}: in-stage vs report".format(stage))
                rpt = "no in-stage .rpt"
                if instage_rpt:
                    with open(instage_rpt) as a, open(report_rpt) as b:
                        self.assertEqual(
                            a.read(), b.read(), "{}: .rpt text".format(stage)
                        )
                    rpt = ".rpt identical"
                print("{}: {} metrics equal, {}".format(stage, len(report), rpt))


if __name__ == "__main__":
    MetricsSplitTest.cases = parse_args(sys.argv[1:])
    unittest.main(argv=sys.argv[:1])
