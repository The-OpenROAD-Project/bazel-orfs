#!/usr/bin/env bash
set -u -o pipefail

# Fetch all remotes
git fetch --all --quiet --prune

# Detect the primary baseline branch on origin
get_origin_primary() {
    if git rev-parse --verify origin/main >/dev/null 2>&1; then
        echo "origin/main"
    elif git rev-parse --verify origin/master >/dev/null 2>&1; then
        echo "origin/master"
    else
        echo "origin/main"
    fi
}

BASELINE=$(get_origin_primary)
OUTPUT_LINES=()
declare -A REMOTE_GROUPS

# Process all remote branches
for br in $(git branch -r --list | grep -v '\->'); do
    if [ "$br" = "$BASELINE" ]; then
        continue
    fi

    # Check for unique commits against origin/main or origin/master
    DIFF_COUNT=$(git cherry "$BASELINE" "$br" | grep "^+" | wc -l)
    
    if [ "$DIFF_COUNT" -eq 0 ] && [[ ! "$br" =~ (.*/main|.*/master)$ ]]; then
        OUTPUT_LINES+=("EMPTY: 🗑️  $br is EMPTY")
        
        # Parse remote and branch name (e.g., "origin/feature" -> remote="origin", branch="feature")
        REMOTE_NAME="${br%%/*}"
        BRANCH_ONLY="${br#*/}"
        REMOTE_GROUPS["$REMOTE_NAME"]+="$BRANCH_ONLY "
    else
        OUTPUT_LINES+=("ACTIVE: 🌱 $br is ACTIVE ($DIFF_COUNT unique commits)")
    fi
done

# Print Status
for line in "${OUTPUT_LINES[@]}"; do [[ $line == ACTIVE:* ]] && echo "$line"; done
for line in "${OUTPUT_LINES[@]}"; do [[ $line == EMPTY:* ]] && echo "$line"; done

# Generate Deletion Commands
if [ ${#REMOTE_GROUPS[@]} -eq 0 ]; then
    echo -e "\nNo empty branches found."
    exit 0
fi

echo -e "\nTo delete these branches from their respective remotes, run:\n"

for remote in "${!REMOTE_GROUPS[@]}"; do
    echo "git push $remote --delete ${REMOTE_GROUPS[$remote]}"
done
