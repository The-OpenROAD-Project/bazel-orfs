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

`GEMINI.md` in the repo root is likewise a symlink to `CLAUDE.md`.

Every playbook is a skill under `.claude/skills`; there are no
`.claude/commands` left, so there is no `commands` or `rules` link to keep.
