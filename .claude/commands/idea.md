> **Repo**: Creates files and commits in openroad-demo. Verify cwd is the openroad-demo root before writing or committing.

Capture a new idea and add it to the ideas/ directory.

## Workflow

1. **Check for duplicates**: Read `ideas/README.md` and scan existing idea
   files in `ideas/` to ensure this isn't already captured.

2. **Create the idea file**: Write `ideas/<slug>.md` with:

   ```markdown
   # <Title>

   ## Problem
   <What's wrong or missing — concrete, specific>

   ## Idea
   <The proposed improvement — what would change>

   ## Impact
   <Who benefits and how much — quantify if possible>

   ## Effort
   <Rough estimate: trivial / small / medium / large>
   ```

   The slug should be lowercase-hyphenated (e.g. `shared-disk-cache.md`).

3. **Update the index**: Add a one-line entry to `ideas/README.md` under
   `## Index`:

   ```markdown
   - [Title](slug.md) — one-sentence summary
   ```

   Check for duplicates before adding. If a similar idea exists, update
   the existing file instead of creating a new one.

4. **Commit**: `git add ideas/ && git commit -m "idea: <title>"`

ARGUMENTS: $ARGUMENTS
