#!/bin/bash
# Deploy a floorplan lane for every flow in flows.txt; one line of status each.
cd "$(dirname "$0")/../.."
log=${LOG_DIR:?}
while read -r flow; do
  name=$(echo "$flow" | tr '/:@' '___')
  if [ -d "tmp/${flow}" ]; then echo "SKIP $flow"; continue; fi
  start=$(date +%s)
  timeout 1800 bazelisk run //:deps -- start "$flow" floorplan > "$log/deploy_$name.log" 2>&1
  echo "DONE $flow exit=$? $(( $(date +%s) - start ))s"
done < test/mpl_exact/flows.txt
echo ALLDONE
