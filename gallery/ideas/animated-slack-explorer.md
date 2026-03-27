# Animated Slack Explorer

Builds on [Immutable ODB with Command Journal](immutable-odb-command-journal.md).

## Problem

Engineers iterate on timing closure across dozens of experiments but have no
way to visually understand how metrics evolve over time or across runs.
Questions like "when did WNS regress?", "which change helped TNS the most?",
and "what does the endpoint slack distribution look like before vs after?" all
require manually scraping logs and building one-off plots. There is no
interactive tool to explore these trends or attribute changes to specific
commands.

## Idea

A web UI that reads KPIs (WNS, TNS, slack histograms, DRV count, area, etc.)
from command-journal-enabled .odb files and presents them as interactive,
time-series visualizations:

- **WNS / TNS / area over time**: line charts across stages or experiments,
  with hover to see the exact command or config change at each point
- **Animated endpoint slack histogram**: scrub through stages (floorplan →
  place → CTS → route) and watch the slack distribution shift — makes it
  obvious where timing degrades
- **Regression detection**: highlight runs where a metric worsened compared
  to baseline, with automatic bisection to the responsible stage/command
- **"What helped / what didn't" annotations**: users tag experiment diffs
  (e.g. "increased CTS buffer distance") and the UI correlates them with
  metric changes, building a knowledge base of effective tuning strategies
- **Slack endpoint drill-down**: click a histogram bin to see which endpoints
  are in that bucket, trace back to the placement or routing decision

Data source: properties embedded in .odb by the command journal, or extracted
from ORFS log files as a fallback before journal support lands.

## Impact

- **Faster timing closure**: visual feedback loop replaces guess-and-rebuild
- **Knowledge capture**: annotations turn tribal knowledge into searchable data
- **Regression triage**: animated histograms make regressions jump out instead
  of hiding in tables of numbers
- **Onboarding**: new engineers see how metrics evolve through the flow instead
  of memorizing stage names

## Effort

Medium — phased:
1. Static plots from ORFS log scraping (small, works today)
2. Interactive time-series with stage scrubber (medium, needs frontend)
3. Animated slack histogram (medium, needs per-stage slack data)
4. Annotation system and regression detection (medium)
5. Full .odb journal integration once command journal lands (small delta)
