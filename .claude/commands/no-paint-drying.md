> **Repo**: Applies to every task in this workspace that involves a build, a flow stage, a sweep or a measurement longer than a few minutes.

Do not make the human watch paint dry. Settling a question with the human is worth more than another hour of gnawing on data, fetching things or waiting on a long run. Long turnaround and open questions never overlap.

ARGUMENTS: $ARGUMENTS

## The rule

1. **Questions first, at small scale.** When a decision depends on a measurement, design the smallest experiment that settles it in seconds to minutes: a synthetic design, a reduced grid, a single stage on a checkpoint, a unit test. Run it, show the number, settle the question with the human. Iterate at that scale until every open question is closed.
2. **Then declare the long run, and its length.** When nothing is left that a fast experiment can answer, say so in one sentence: "there is nothing for it, the big run has to happen; I need no input from you for the next N hours." Launch it unattended, with a monitor, a timeout, a memory cap and a result file that fills in as it goes, so a kill halfway is still a result.
3. **Never both at once.** A long run that raises a question the human must answer before it can continue is a design error: the question belonged in step 1. If one comes up anyway, write it down, let the run finish or kill it, and settle the question at small scale before relaunching.
4. **Report, do not narrate.** While a long run is out, the human gets a message when something changes state or something sticks out by a multiple, not a heartbeat. Idle ticks are silent.

## What it looks like

- A global-route optimisation is designed on a wirebound variant that routes in 30 s, with the human choosing the knobs; the overnight matrix on the 3.6 mm XiangShan die runs every combination without a single prompt and produces one table in the morning.
- A parallel-synthesis dependency question is settled with `aquery` on one block in seconds, not by relaunching a 34-block build and waiting to see what re-runs.
- A legaliser failure is diagnosed on the placement checkpoint through the odb-debug daemon while the flow keeps running, and the floorplan fix is chosen before anything is relaunched.

## Anti-patterns

- Launching the full design to "see where it gets stuck next" when the previous run already showed where.
- Polling a running job every few minutes and telling the human each time that nothing changed.
- Answering a question the human asked with "let me start a run and come back in an hour" when a smaller run, a log already on disk or a grep of the source would answer it now.
- A sweep whose arms each need a human decision between them.

## Where the mechanics live

`/openroad-debug` for the `_deps` and bring-your-own-binary loop that makes a stage a seconds-scale experiment; `/odb-debug` for questions the ODB answers without re-running anything; `debug-rtl-sim` for the simulation ladder. This skill decides the order and the moment to stop asking; those decide how.
