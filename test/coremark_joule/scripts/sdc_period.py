"""The clock period in a design's constraints.sdc, and what follows from it.

The period is one fact with several consumers: the flow builds at it,
the simulator times the SAIF by it, and the energy number divides by the
frequency it implies. Each consumer used to carry its own copy -- a
literal in a BUILD file, maintained by hand, next to a comment saying it
must agree with the SDC.

Both copies drifted, and neither failure was detectable downstream:

- the reported frequency disagreed with the period ibex was built at, so
  the study published a core at 833 MHz on a netlist that missed its
  period by 74 ps (5.5);
- the simulator's period disagreed after auto_period repinned the SDCs,
  so every SAIF was timed against the old clock. OpenSTA reads a SAIF as
  transitions divided by duration, so picorv32's toggle rates came out
  at less than half their true value, and the power with them.

So the period has one reader, here, and every consumer calls it.
"""

import re

_CLK_PERIOD = re.compile(r"^(\s*set\s+clk_period\s+)(\d+)(\s*(?:;.*|#.*)?)$", re.M)


class NoPeriod(Exception):
    """The constraints do not state a period this module can read."""


def period_ps(sdc_text):
    """The period in picoseconds."""
    m = _CLK_PERIOD.search(sdc_text)
    if not m:
        raise NoPeriod("no `set clk_period <ps>` line in the constraints")
    return int(m.group(2))


def frequency_mhz(sdc_text):
    """The frequency the period implies."""
    return 1.0e6 / period_ps(sdc_text)


def set_period_ps(sdc_text, ps):
    """Rewrite the period, leaving every other byte of the file alone."""
    if ps <= 0:
        raise NoPeriod("refusing to write a period of %r ps" % ps)
    new, n = _CLK_PERIOD.subn(lambda m: m.group(1) + str(ps) + m.group(3), sdc_text)
    if n != 1:
        raise NoPeriod("expected exactly one `set clk_period` line, found %d" % n)
    return new
