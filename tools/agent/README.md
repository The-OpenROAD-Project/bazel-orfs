# The bazel-orfs agent channel

An agent working in a workspace that depends on bazel-orfs gets what an
agent working in bazel-orfs itself has: the skills for building and
debugging ORFS flows, the rules they rest on, and the odb-debug MCP
server. All three come from the bazel-orfs source Bazel fetched for the
version `MODULE.bazel` pins, so a bump updates them with the flow code and
rolling the pin back rolls them back.

## Set up once

```sh
bazelisk run @bazel-orfs//:agent -- setup
git add .mcp.json .claude/settings.json CLAUDE.md
```

`setup` writes three committed entries and refuses, naming the file, when
one is already there and says something else:

| file | entry |
|---|---|
| `.mcp.json` | the `odb-debug` server: `python3 .claude/bazel-orfs/tools/odb_debug/mcp_server.py` |
| `.claude/settings.json` | a `SessionStart` hook: `bazelisk run @bazel-orfs//:agent -- sync --hook` |
| `CLAUDE.md` | `@.claude/bazel-orfs/docs/agent-rules.md` |

## Every session

The hook runs `sync`, which makes links, never copies:

```
.claude/bazel-orfs       -> <output_base>/external/bazel-orfs+
.claude/skills/<name>    -> ../bazel-orfs/.claude/skills/<name>
```

The links are kept out of git in the clone's `.git/info/exclude`, since
they point into this machine's output base. When the set of exported
skills changed, the hook asks Claude Code to reload its skills, so a bump
shows in the same session. A build holding the Bazel lock delays the hook
by at most its 60 s timeout; the session then starts on the links the
last sync made, which already show the fetched source.

A skill of the workspace's own with an exported name is refused, not
replaced: rename one of them.

## What is exported

`EXPORTED_SKILLS` in `agent.py`. Every skill in `.claude/skills` is either
exported or listed in `INTERNAL_SKILLS` (bazel-orfs's own pull requests
and studies, and workflows written for another checkout's layout);
`//tools/agent:agent_test` holds the two lists equal to the directory, and
checks that an exported skill reads the same through a link: no relative
link out of its directory, and bazel-orfs's targets named
`@bazel-orfs//...`, which resolves in bazel-orfs and in every workspace
that depends on it.

The rules are `docs/agent-rules.md`, which bazel-orfs's own `CLAUDE.md`
imports too.
