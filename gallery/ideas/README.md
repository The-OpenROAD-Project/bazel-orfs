# Ideas

Ideas for improving openroad-demo, OpenROAD, and the EDA workflow.

Each idea is a separate `.md` file in this directory. Add new ideas with
`/idea <title>` or create a file manually.

## Index

- [Immutable ODB with Command Journal](immutable-odb-command-journal.md) — Embed Tcl command history in .odb files for debugging, replay, and KPI mining
- [Animated Slack Explorer](animated-slack-explorer.md) — Interactive UI to plot WNS/TNS over time, animate slack histograms across stages, and annotate what helped
- [Static HTML Facsimile of the OpenROAD Web Viewer](static-html-gui.md) — Pre-rendered static HTML snapshots of the web viewer (histograms, timing, layout) with zero click-and-wait
- [Claude-Augmented Git Flow](claude-augmented-git-flow.md) — Workflow philosophy where FRs are the primary artifact and Claude bridges ideas to mergeable code
- [Fast Unit Test cc_library Extraction](fast-unit-test-cc-library-extraction.md) — Extract testable classes from monolithic OpenROAD modules so unit tests compile in seconds
- [Auto-select Gallery Stage](auto-gallery-stage.md) — Gallery image should come from latest successful stage, not hardcoded in BUILD
- [Per-Stage OpenROAD Binaries](per-stage-openroad-binaries.md) — One stripped-down openroad binary per ORFS stage for faster rebuild iteration
- [Per-Command OpenROAD Binaries](per-command-openroad-binaries.md) — Standalone cc_binary per command for fast rebuild, direct gdb, and reproducible bug reports
- [Mock Yosys and OpenROAD](mock-yosys-openroad.md) — Python scripts that validate EDA configuration in seconds by mocking synthesis and P&R with heuristic estimates
