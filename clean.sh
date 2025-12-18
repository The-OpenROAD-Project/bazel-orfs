#!/usr/bin/env bash

git fetch origin --quiet && git branch -r --list origin/* | grep -v '\->' | while read br; do \
    DIFF_COUNT=$(git cherry HEAD "$br" | grep "^+" | wc -l); \
    if [ "$DIFF_COUNT" -eq 0 ]; then \
        echo "🗑️  ${br#origin/} is EMPTY (Fully merged/cherry-picked)"; \
    else \
        echo "🌱 ${br#origin/} is ACTIVE ($DIFF_COUNT unique commits)"; \
    fi; \
done
