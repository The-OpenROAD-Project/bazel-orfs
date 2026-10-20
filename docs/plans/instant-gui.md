# A warm GUI, a click away

The web viewer (`openroad -web`, `web_server`) is the GUI. On a large
design it takes tens of minutes from `read_db` to a viewer that answers
without click-and-wait: the ODB, the liberty set, the macro netlists
when the `.lib` abstracts are not accurate enough, parasitics and the
first timing update. That path has had its easy wins; it will not get
an order of magnitude faster.

So hide it instead. A build ends, the design loads in the background
while the human reads the build's summary, and when they want to look,
the GUI is one click away.

## Proposal

The odb-debug daemon (`tools/odb_debug`) already was a warm, headless
`web_server` that a browser attaches to. What it lacked, and now has
(`tools/odb_debug/README.md`, "Look at it"; the `warm-gui` skill):

1. **The MCP server starts it.** A tool `open(target)` runs
   `bazelisk run <target>_odb_debug` detached and returns at once;
   `status` says `loading`, then `ready` with the link. An agent session
   asks for the GUI the way it asks any other question.
2. **No idle exit while the GUI waits.** Once loaded, the daemon does
   not exit on idle until the first interaction, from the agent session
   or the browser; from then on the normal idle rule holds. While it
   waits, its watchdog checks rarely. Browser requests count as
   interaction.
3. **A link that works over a VPN.** The daemon stays bound to
   loopback: the viewer evaluates any Tcl it is sent and has no
   authentication. A small proxy (stock `python3`, outliving the agent
   session) listens on the address the human's ssh session came in on
   (the third field of `$SSH_CONNECTION`) and forwards only requests
   that carry a random token from the link. The token lives in
   `daemon.json`, readable by the owner only. This is the quick way to
   get there; once it works, a nicer one (a `web_server -token` in
   OpenROAD, say) can replace it.
4. **A skill that warms what comes next.** After a build, `warm-gui`
   picks the likeliest stage (the one the command named; else `final`;
   after a failure, the last one that succeeded), calls `open`, and
   tells the human how to open the GUI: click the link over the VPN,
   what to check when it does not connect, and an `ssh -L` tunnel to
   the link's port only when the machine cannot be reached at all. The warm session is not in the Bazel cache, and the
   skill says so.

First tried on ORFS's asap7 `gcd`, its final stage
(`//test/odb_debug:gcd_final_odb_debug`), on a workstation.

Not done: an `odb_debug()` companion for every stage of every
`orfs_flow`, so the skill never has to add one first.

## Alternatives considered

| Option | Verdict |
|---|---|
| Keep a warm headless `web_server` after the build (above) | **Chosen.** Nothing is serialized, so OpenROAD maintainers get no new contract; already built as odb-debug; testable in seconds. |
| CRIU checkpoint of the warmed, headless process, CRaC-style (close the listener and files before the dump, reopen after restore) | Rejected. Survives a reboot and restores near-instantly with lazy pages, but needs `setcap cap_checkpoint_restore` on every machine and criu, which Ubuntu 24.04 does not package: bazelisk is the only thing a consumer may need to install. Images are many GB, tied to the binary, and not shareable through the Bazel cache. |
| Save OpenSTA's state (graph, arrivals, parasitics) to disk, pdumper-style | Rejected. About a hundred classes in upstream OpenSTA, and a versioned format to maintain forever; PrimeTime sessions do not even restore across versions. |
| Persistent mmap heap (Metall, Boost.Interprocess) | Rejected. Forbids raw pointers and virtual classes: a rewrite of OpenSTA. |
| Zygote/fork server: load once, fork a session per viewer | Rejected. Forking after the thread pools have started is unsafe, and it gains nothing over a warm server. |
| DMTCP | Rejected. Research-grade; X needs it to checkpoint a VNC server alongside. |
| Static snapshot of results (worst paths, slacks) | Rejected. Answers only the questions asked at build time; wandering a design is exactly what it cannot do. |
| Qt GUI under xpra, Qt `-platform vnc`/`webgl` | Moot: the web viewer replaces the Qt GUI. |
| Faster loading | Moot: no easy win is left on the load and warm-up path. |
