"""The potential report's literature column: what a structure should cost.

Every row is a published number for a named configuration, converted to
fanout-of-four inverter delays (FO4) so it carries across technologies.
The conversion is Hrishikesh et al.'s: one FO4 is about 360 ps times the
drawn gate length in microns [H02, footnote 1, after Horowitz]. A row
whose configuration differs from the structure it is compared with says
so in `scope`; the comparison is then an order of magnitude, not a band.

[P97] S. Palacharla, N. P. Jouppi, J. E. Smith, "Complexity-Effective
      Superscalar Processors", ISCA 1997, pp. 206-218. Table 2: overall
      delay results, Spice on 0.8, 0.35 and 0.18 um layouts.
[H02] M. S. Hrishikesh, N. P. Jouppi, K. I. Farkas, D. Burger,
      S. W. Keckler, P. Shivakumar, "The Optimal Logic Depth per Pipeline
      Stage is 6 to 8 FO4 Inverter Delays", ISCA 2002. Section 3: CACTI
      3.0 access times of Alpha 21264-sized structures at 100 nm.
[MPR96] Microprocessor Report vol. 10 no. 14, 1996, on the 21264: the
      integer register file is duplicated, each copy 80 entries with four
      read and six write ports.
"""


def fo4_ps(drawn_um):
    """One FO4 in ps for a drawn gate length in microns [H02]."""
    return 360.0 * drawn_um


def row(name, ps, drawn_um, source, scope):
    return {
        "name": name,
        "ps": ps,
        "drawn_um": drawn_um,
        "fo4": round(ps / fo4_ps(drawn_um), 1),
        "source": source,
        "scope": scope,
    }


MODELS = [
    row(
        "register file, Alpha 21264 integer (80 x 64, 4R 6W)",
        390.0,
        0.10,
        "H02 s3.3, CACTI 3.0",
        "access time; H02 matched capacities to the 21264, ports per MPR96",
    ),
    row(
        "issue window wakeup + select, 4-wide, 32 entries",
        578.0,
        0.18,
        "P97 Table 2",
        "Spice, 0.18 um",
    ),
    row(
        "issue window wakeup + select, 8-wide, 64 entries",
        724.0,
        0.18,
        "P97 Table 2",
        "Spice, 0.18 um",
    ),
    row("rename (RAM scheme), 4-wide", 351.0, 0.18, "P97 Table 2", "Spice, 0.18 um"),
    row("rename (RAM scheme), 8-wide", 427.9, 0.18, "P97 Table 2", "Spice, 0.18 um"),
    row(
        "bypass, 8-wide",
        1056.4,
        0.18,
        "P97 Table 2",
        "result-bus wire delay; does not scale with feature size",
    ),
]


def by_name(prefix):
    return [m for m in MODELS if m["name"].startswith(prefix)]


if __name__ == "__main__":
    for m in MODELS:
        print(
            "%-55s %7.1f ps @ %.2f um = %5.1f FO4  [%s]"
            % (m["name"], m["ps"], m["drawn_um"], m["fo4"], m["source"])
        )
