# Philosophy

The point of this project is not "look, I made Claude do something." Getting
Claude to run a flow is not where the value is. The value is in building a
mental model of what the flow actually does.

This project sets up a lab environment where you can ask Claude to explain
error messages, warnings, and timing reports one concept at a time. Claude
handles the scaffolding so you can focus on understanding rather than fighting
toolchain setup — provided you stay engaged rather than drifting into
["agent psychosis"](https://www.fast.ai/posts/2026-01-28-dark-flow/).
As Ethan Mollick
[argues](https://www.oneusefulthing.org/p/against-brain-damage), the default
mode of AI is to do the work for you, not with you — but used deliberately,
it can push you to think through problems yourself. The goal here is to reduce
noise, not to reduce thinking.

## No-estimates

This is a **no-estimates project** — but not in the usual sense. Traditional
projects avoid estimates because they become negotiations: someone asks "how
long?", someone answers defensively, and the number becomes a commitment rather
than information. Here, AI closes the loop. Claude can generate build time
estimates for free based on actual data (see [build_times.yaml](build_times.yaml)),
and those estimates improve as more projects are added. When estimates are cheap
to produce and grounded in real measurements, they stop being political and
start being useful.

The data lives in your own repository — [build_times.yaml](build_times.yaml)
tracks per-stage durations, the projects table records cell counts and
frequencies, and git history captures velocity. Claude can read all of this
and generate a Gantt chart for what you plan to do next, informed by how long
similar work actually took. The estimate comes from your data, not from a
meeting.

## Capturing knowledge, not automating builds

This project is not traditional automation. The goal is not to script a
push-button flow that runs unattended — it is to use Claude and a skilled
operator together to capture skills, metadata, and failure modes for each
project, then ask Claude to write scripts and reports that mine this data for
interesting patterns.

The scripts and data are deliberately lightweight. A project README records
qualitative observations (what was tried, what broke, what the critical path
looks like) alongside quantitative metrics (per-stage build times, WNS, cell
counts, memory usage). Each entry is the result of many one-off trials with
the specific versions of bazel-orfs, OpenROAD, and ORFS at the time — yet
everything is reproducible through the git log, because the project table pins
each contribution to a commit hash.

Over time, the accumulated READMEs, metrics, and logs form a corpus that Claude
can query across projects: "which designs hit OOM during routing?", "how does
placement density correlate with routing time?", "what slack margin was needed
for designs with WNS worse than -500ps?" The answers come from real data, not
from rules of thumb.

This is a pseudo-random walk through design space. The scripting does not need
to be robust — Claude and a skilled operator will manually tweak things to work
when working on a particular design. It is a messy lab log. The idea is that
something useful can be gleaned from it later, with Claude automating the
reading of these messy logs and summarizing them in various ad-hoc ways. Since
all of the information is designed to be consumable by Claude, the data is kept
small in size — lightweight metrics, compact log summaries, and structured
READMEs rather than multi-gigabyte build artifacts.

The result is cached, semi-organized information from long runs and various lab
experiments — gold for Claude. Build logs, JSON metrics, timing reports, and
README narratives accumulate over time. Each piece is small and self-describing,
but together they form a corpus that would take a human hours to cross-reference.
Claude can read all of it in seconds and answer questions that span multiple
projects, versions, and failure modes.

The goal is to collect the best data available at the time, not to have
something consistent. Consistency would be too expensive — it would mean
re-running every project whenever a metric definition changes or a new stage
is added. The best plan now, with incomplete information, beats a perfect plan
later with perfect information. A gemmini README that records "OOM'd at 90%
of routing iteration 0, peak 28.9 GB" is more useful today than waiting until
we have a 64 GB machine to produce a clean final report.

The operator's role is to notice what is surprising or non-obvious during a
build and ensure it gets recorded. Claude's role is to structure that
information so it can be compared, queried, and acted on later. Neither role
works well alone — automation without judgment records noise, and judgment
without tooling forgets.

## Scalable RTL is a prerequisite

Even if the exact final design parameters are known to a certainty, a project
is in trouble if the RTL is not scalable. When a full build takes 6 hours and
29 GB of RAM, every experiment is a day-long commitment. You cannot develop a
backend strategy by learning from builds that take hours — the feedback loop
is too slow to explore the design space.

Scalable RTL lets you create configurations at different scales: a minutes-scale
version (~5-10K cells) that reveals synthesis and floorplan issues, a
tens-of-minutes version (~50-100K cells) that reveals timing closure and routing
challenges, and only then the full design. Each scale teaches different lessons.
The small version of Gemmini (4×4, 47K cells) completed in minutes where the
full 16×16 (896K cells) OOM'd after 6 hours of routing — and the small version
revealed the same -185ps WNS pattern, letting us tune slack margins at a
fraction of the cost.

Designs that are not parameterizable — fixed-size RTL that can only be built
at full scale — are at a structural disadvantage. The turnaround time becomes
the bottleneck, not the tooling.

## Broken != stuck, broken != urgent

Chasing a stable EDA toolchain is chasing a mirage. The cost skyrockets
and delays are inevitable. A perfect tool that can only build solutions
that are worthless is worthless. An imperfect tool that can be extended
for use cases that don't exist yet — that's what compounds.

Anything worth doing in EDA has not been done before, or it wouldn't be
worth doing. We push forward with patches, not wait for releases.

When the flow hits a bug, the response is not to stop and wait. It is:

1. Diagnose — find the root cause, whittle to a minimal reproducer.
2. File — create a quality issue with a patch and a C++ unit test.
3. Unblock — apply the same patch locally and keep building.
4. Advance — hit the next bug. Repeat.

This is an induction proof. The base case: the design fails at one
stage, we fix it, the design advances. The inductive step: at each new
failure, we diagnose, file, and advance. The fix for step N does not
depend on the fix for step N+1 being known. Each step is self-contained.

The induction hypothesis is: "for any bug we encounter, we can diagnose
it, create a minimal reproducer, write a fix, and continue." Each
resolved bug is evidence for the hypothesis — not proof that no more bugs
exist, but proof that the process works. The chain grows monotonically.
That's velocity.

The project's velocity is built on upstream investment. Every issue
filed, every patch tested, every workaround documented is a layer of
bedrock. When patches merge, workarounds disappear and the flow gets
simpler — not more fragile. We are not building on sand.

## CI-less by design

This is a **CI-less project by design**. No source code is uploaded, and demo
projects are immutable — the projects table lists the git hash of each
contribution, so results can always be reproduced at that exact version. An
updated project is effectively a new project; there is nothing to regress.
We use a self-hosted reviewer Claude skill (`/review`) instead of CI.

It is intentionally light to host and maintain.
