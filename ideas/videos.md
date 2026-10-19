# Videos about bazel-orfs

Status: **one made, the rest proposed.** The first is the short hook,
*ORFS, at the speed of your ideas* (`docs/demos/warm_gui`). Everything
else below waits for it to land well.

## What the first attempts taught

Three earlier cuts of the first video failed, and the reasons are the
rules for every video after it:

- **One idea per video.** A 3-minute cut with eleven ideas could not be
  followed. Each item below is its own video.
- **Slow.** The failed cut ran at 167 words a minute with the narrator
  speaking 94% of the time. Aim for about 120, with a second between
  sentences and longer between scenes.
- **One thing to read.** A headline of a few words on screen; the full
  sentence goes in the subtitles, not burned into the picture.
- **Short sentences, one idea each.** No colons or semicolons in what
  is spoken.
- **Graphics carry data, or there are none.** A hillside with no numbers
  illustrated nothing; a gauge whose meaning changed between scenes
  added load.
- **Build on ORFS, never against it.** bazel-orfs is ORFS with a memory.
  The benefit is said in its own terms; "pain", "hassle" and "waiting"
  are not the frame.
- **A person narrates.** The synthetic voice is for drafts.
- **A 30-second sample before any full render.**
- **Reviewers who know ORFS and not Bazel read the script first.** Three
  of them (a student, a design-space explorer, an OpenROAD contributor)
  asked for the comparison with `make`, measured cache hits rather than
  added-up stage times, and less mechanics. They were right.
- **Every number is measured, or says where it comes from.**

## Measurements on hand

asap7 riscv32i, one 16-core 30 GB machine, each run once, 2026-10-19:

| What | Time |
|---|---|
| Stages by hand in the dirty lane: floorplan, place, cts, grt, route, final | 28, 26, 31, 49, 214, 13 s (361 s; 134 s to grt) |
| `bazelisk build`, synthesis to final, cold | 359 s |
| A placement change, Bazel, to final / to grt | 324 s / 191 s |
| The same three stages to grt by hand | 106 s (Bazel adds about 85 s here, not yet explained) |
| Switching back to the earlier setting | 0.8 s to final, 1.9 s to grt |
| A fresh output base served by a team cache, nothing run | 234 s, 1.2 GB |
| Editing `global_place.tcl`: `make do-3_3_place_gp` in the dirty lane | 12 s |

From earlier work, with sources: asap7 ibex substeps (study PR #968);
XiangShan's XSTile stages, floorplan 11 min, place 225 min, cts 45 min,
grt 42 min (`resources.json`); "about six hours cold" (the XiangShan
README); repair shares and coralnpu's convergence shape (OpenROAD
#11684).

## Proposed videos

Each with the one point it makes, its audience, and what it needs.

**Your design in bazel-orfs.** *Point:* a design is a few lines next to
its RTL, and ORFS's own `config.mk` is read as it stands. *Audience:*
ORFS users. *Covers:* `orfs_flow()`, `config.mk` as a small language
(DSL) and how its variables map to the flow, your AI writing the BUILD
files while you review the diff, pins and `//:bump`. *Needs:* nothing
new.

**Stop where the decision is.** *Point:* by global route you have
nearly everything a decision needs; detailed route is for the build you
tape out. *Audience:* design-space explorers. *Covers:* the landscape
(big problems early, candidates a few percent apart near WNS = 0, small
numbers that look like big percentages), thirty years of predicting
routing without routing. *Needs:* the history checked against papers
and acquisition records before anything is named.

**Exploring a design.** *Point:* sweeps share their early stages, and an
optimizer runs a flow Bazel built once. *Audience:* architects and
researchers. *Covers:* `orfs_sweep`, `orfs_run_executable`, `fork`, the
estimation ladder, synthesis time on XiangShan (slang, patch 0079,
hardened macros). *Needs:* a bigger design measured the same way
(`swerv_wrapper` or similar), a real sweep with end-to-end time and disk
use, power numbers.

**What a cache adds to make.** *Point:* `make` reruns from a stage; the
cache adds switching back, results shared by a team and CI, and not
having to know what to clean. *Audience:* ORFS and OpenROAD
contributors. *Covers:* `bazelisk build` sealed and `bazelisk run` in
your environment, dependencies kept simple on purpose with the dirty
lane for precision, a remembered result as one valid result (not a
promise of identical bits), the team cache. *Needs:* an explanation of
the 85 s Bazel overhead on riscv32i, a cache-hit time on XiangShan.

**When is repair done?** *Point:* repair is most of the real work, and
when to stop it is a policy with no oracle. *Audience:* OpenROAD
developers. *Covers:* OpenROAD #11684's table and examples (coralnpu's
late jump, cva6's 6.9 ps). *Needs:* a real `repair_timing -verbose`
convergence curve from one of our runs.

**The warm GUI.** *Point:* after a build the design is already loaded,
one click away from your laptop over a VPN. *Covers:* `bazelisk run …
gui_<stage>`, the token link, the warm-gui skill. *Needs:* a load time
on a large design, if we choose to state one.

**AI on a large OpenROAD project.** *Point:* an agent is limited by
decisions per hour, like a person, and by what it reads. *Covers:*
context explosion (money, time, quality), asking a warm session for
summaries, making your own MCP server. *Needs:* a measured token count,
a raw report against its summary.

**Carrying a fix upstream.** *Point:* carry a fix as a patch, prove it
across ORFS's designs, then propose it. *Audience:* contributors and
maintainers. *Covers:* carried patches, the sweep as a test bench, the
human decision, draft pull requests with data, verifying what an AI
reviewer claims. *Needs:* one real example end to end.
