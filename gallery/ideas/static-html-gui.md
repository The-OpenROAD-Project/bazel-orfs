# Static HTML Facsimile of the OpenROAD Web Viewer

[PR #9770](https://github.com/The-OpenROAD-Project/OpenROAD/pull/9770) —
[Vision doc](https://github.com/Pinata-Consulting/OpenROAD/blob/4e360862de8aff41d4daca82eb41bee07b780bb6/docs/html_vision.md)

## Use-case

Run a build overnight. Next morning, open a static HTML file and instantly
inspect everything — histograms, timing paths, layout, clock tree — with
zero wait because all data is pre-computed.

## Absolute requirement

**Zero click-and-wait.** The static HTML page must never fetch, compute, or
block. Every visible element is a pre-rendered snapshot. No WebSocket, no
promises, no "Update" buttons, no "Loading..." spinners. Open the file,
everything is there.

## Problem

The OpenROAD Qt GUI and the live web viewer (`src/web/`) both require a
running OpenROAD process with the full design loaded into memory.

- **Click and wait**: loading the design + recomputing timing takes minutes
  per stage, repeated every time you switch designs or experiments
- **CI/CD**: overnight builds produce .odb files but no visual inspection
  without manually launching the GUI the next morning
- **Sharing**: "look at this histogram" means a screenshot — no URL to send
- **Diffing**: comparing two experiments means two GUI windows; there's no
  `diff` for visual reports
- **Air-gapped / remote environments**: cloud build farms, SSH sessions, and
  locked-down fabs have no display server

## Architecture — refactoring the web viewer

The web viewer (`src/web/`) already has pure layout functions extracted for
testability:

- `computeHistogramLayout()` in `charts-widget.js`
- `computeClockTreeLayout()` in `clock-tree-widget.js`
- Canvas rendering, HTML table generation, tree building — all in JS
- Same CSS and theme system (`style.css`, `theme.js`)

The refactoring makes these pure functions serve both modes:

```
Web viewer JS pure functions (shared rendering code)
    │
    ├── Live mode: WebSocket → data → pure functions → canvas/DOM
    │
    └── Static mode: build-time data extraction → same pure functions
        → pre-rendered SVG / PNG / HTML tables inlined in one .html file
```

**Not a DataProvider / proxy pattern.** Static mode doesn't call `request()`
at all. The build step runs the pure functions once, produces the visual
output, and embeds it. The result is a snapshot, not a lazy-loading viewer.

### What gets snapshot at build time

| Widget | Live mode | Static snapshot |
|--------|-----------|-----------------|
| Slack histogram | Canvas drawn after "Update" click | SVG rendered by `computeHistogramLayout` at build time |
| Timing paths | Table populated after "Update" click | Static `<table>` with all paths pre-rendered |
| Clock tree | Canvas drawn after clock selection | SVG rendered by `computeClockTreeLayout` at build time |
| Hierarchy | Tree populated on WebSocket load | Full tree pre-expanded as static HTML |
| Layout viewer | WebSocket tiles on scroll | Pre-rendered tile pyramid (PNG), offline Leaflet |
| Inspector | Populated on click | Top-level design properties pre-rendered |
| Tcl console | Interactive prompt | "Read-only snapshot" message or omitted |

### Build pipeline

1. Load design in OpenROAD, extract data as JSON (same format the
   WebSocket handlers produce: bounds, tech, slack_histogram,
   timing_report, clock_tree, module_hierarchy, etc.)
2. Run JS pure functions via Node.js against that JSON
3. Render to SVG (charts), static HTML (tables/trees), or PNG (tiles)
4. Inline everything into a single self-contained `.html` file — no
   server, no dependencies, no CDN

### Why JS pure functions as rendering source of truth

The web viewer's JS already implements the rendering algorithms
(`computeHistogramLayout` matches `chartsWidget.cpp` bucketing, etc.).
JS determines pixel positions, colors, labels for web output. Using the
same functions directly for static output guarantees visual fidelity with
the live viewer.

Qt / C++ remains the source of truth for **data and algorithms** (slack
computation, bucketing logic, path extraction). JS is the source of truth
for **how that data looks in a browser**.

## First step: timing histograms

The timing histogram (slack histogram + timing path table) goes in first.
Maximum impact — it's the most-used inspection in timing closure — and it
forces agreement on the architecture, separation of concerns, and how live
vs. static modes coexist before touching anything else.

PR #9770 demonstrated this as a standalone Python script. The refactored
version:

- Extracts histogram + timing path data from OpenROAD at build time (JSON)
- Runs `computeHistogramLayout()` from `charts-widget.js` via Node.js
- Renders to static SVG + static HTML timing path table
- Produces a single self-contained HTML file

Once this works end-to-end, the pattern is proven and extending to clock
tree, layout tiles, etc. is mechanical.

## Tiered rollout after histograms

Each tier ships independently:

1. **Timing histogram + path table** — first, proves the architecture
2. **Clock tree** — `computeClockTreeLayout` already extracted
3. **Module hierarchy** — static HTML tree
4. **Layout tiles** — pre-rendered PNG pyramid + offline Leaflet
5. **Inspector, DRC, schematics** — remaining widgets

## Prior art

This is a well-established pattern, not novel:

- **Leaflet offline tiles**: `L.tileLayer('./tiles/{z}/{x}/{y}.png')` —
  the exact pattern for serving pre-rendered tiles without a server
- **Plotly `write_html()`**: self-contained HTML with all data + JS inlined
- **Chrome DevTools trace export**: records all interactions, exports as a
  standalone HTML viewer with all data pre-baked
- **Jupyter nbconvert**: renders notebook cells (including charts) into
  static HTML with outputs pre-computed
- **TileServer GL / Martin**: pre-render map tile pyramids for offline use
- **PR #9770**: demonstrated the timing-only case end-to-end

## Time dimension — animated histograms across versions

A single HTML report shows one snapshot. When builds produce reports for
every stage and experiment, the static files become frames in a timeline:

- **Across stages**: scrub floorplan → place → CTS → route and watch the
  endpoint slack distribution shift — makes it obvious where timing degrades
- **Across experiments**: compare parameter sweeps side by side, animated
  in sync
- **Regression detection**: CI stores HTML reports per commit; an index
  page diffs histograms between runs and highlights regressions

This connects to the [Animated Slack Explorer](animated-slack-explorer.md)
idea — the static HTML provides per-snapshot data, and the explorer
stitches snapshots into an interactive timeline. The two compose: individual
reports are useful standalone and more powerful combined.

## Impact

- **No more click and wait**: open the HTML — histograms and tables are
  instant, no loading design, no recomputing timing
- **Every ORFS build gets a visual report for free** — no GUI launch needed
- **Shareable**: attach HTML to a bug report or PR
- **Diffable**: `diff stage1.html stage2.html` or visual diff in browser
- **CI dashboards**: embed timing histograms directly in CI artifacts
- **Onboarding**: new engineers explore designs in a browser without
  installing OpenROAD
- **Air-gap safe**: works offline, no server, no phone-home
- **One rendering codebase**: the live web viewer and the static snapshot
  share the same pure JS functions — no parallel reimplementation that drifts

## Effort

Large — but tiered so each increment ships independently:

1. **Timing histograms** (first — proves the architecture)
2. **Clock tree + hierarchy** (weeks — pure functions already extracted)
3. **Layout tiles** (weeks — Leaflet offline is a known pattern)
4. **Remaining widgets** (months — each follows the same recipe)
