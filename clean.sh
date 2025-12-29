#!/usr/bin/env bash
set -u -o pipefail

git fetch origin --quiet



OUTPUT_LINES=()
EMPTY_BRANCHES=()
CURRENT_BRANCH=main
for br in $(git branch -r --list origin/* | grep -v '\->'); do
    BRANCH_NAME="${br#origin/}"
    # Skip current branch (main/master/etc)
    if [ "$BRANCH_NAME" = "$CURRENT_BRANCH" ]; then
        continue
    fi
    DIFF_COUNT=$(git cherry HEAD "$br" | grep "^+" | wc -l)
    if [ "$DIFF_COUNT" -eq 0 ]; then
        OUTPUT_LINES+=("EMPTY: 🗑️  $BRANCH_NAME is EMPTY (Fully merged/cherry-picked)")
        EMPTY_BRANCHES+=("$BRANCH_NAME")
    else
        OUTPUT_LINES+=("ACTIVE: 🌱 $BRANCH_NAME is ACTIVE ($DIFF_COUNT unique commits)")
    fi
done

# Print ACTIVE first, then EMPTY
for line in "${OUTPUT_LINES[@]}"; do
    if [[ $line == ACTIVE:* ]]; then
        echo "$line"
    fi
done
for line in "${OUTPUT_LINES[@]}"; do
    if [[ $line == EMPTY:* ]]; then
        echo "$line"
    fi
done

if [ ${#EMPTY_BRANCHES[@]} -eq 0 ]; then
    echo -e "\nNo empty branches to delete."
    exit 0
fi
echo -e "\nTo delete empty branches from the server, run:\n\ngit push origin --delete ${EMPTY_BRANCHES[*]}"
