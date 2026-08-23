# Antigravity wiring

Everything here is a symlink into `.claude/`, which is the single source of
truth for agent instructions, skills and guardrail policy. The only real
files are the ones whose *schema* is antigravity-specific and therefore
cannot be shared:

| Path | What it is |
| --- | --- |
| `hooks.json` | antigravity hook registration (its schema differs from `.claude/settings.json`) |
| `scripts/guard_tool.py` | symlink to `../../.claude/hooks/guard_tool.py` — one policy, two hook dialects |
| `skills` | symlink to `../.claude/skills` |
| `commands` | symlink to `../.claude/commands` |
| `rules` | symlink to `../.claude/commands` |

`GEMINI.md` in the repo root is likewise a symlink to `CLAUDE.md`.

## Open question: `rules` vs `commands`

We are not sure which directory antigravity actually reads, nor whether it
treats `rules/` as always-on context or as on-demand playbooks. Claude Code's
`.claude/commands/` are strictly *on-demand* slash commands, and injecting all
of them on every turn would be wasteful.

Both names are symlinked to `commands/` for now so nothing regresses. Once the
contract is known, drop whichever symlink is dead — and if `rules/` turns out
to be always-on, point it at a small dedicated directory instead of the
playbooks.
