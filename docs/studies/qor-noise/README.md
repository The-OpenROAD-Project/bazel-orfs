Results for the QoR-noise study. The write-up is the pull request body;
nothing here is a hand-typed table.

    analysis.json      every number the write-up quotes
    transitions.csv    per-(design, metric) threshold moves, classified
    labels.csv         the Old/New/Type tables from ORFS commit messages
    design_rank.csv    per-design responsiveness and solo-move rate
    figures/           rendered from analysis.json by plots.py

Regenerating these needs an ORFS checkout and about two seconds; the
14 MB intermediate (every threshold record) is not committed because it
is a half-second to rebuild. The commands are in the pull request body.
