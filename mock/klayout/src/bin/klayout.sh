#!/bin/sh
# Mock klayout binary - generates dummy GDS files for testing.
#
# Parses "-rd key=value" arguments to find the output file path
# and creates a minimal dummy GDS file.

next_is_rd=false
for arg in "$@"; do
    if [ "$next_is_rd" = true ]; then
        case "$arg" in
            out=*)
                outfile="${arg#out=}"
                mkdir -p "$(dirname "$outfile")"
                # Write a minimal dummy GDS II file (HEADER + BGNLIB + ENDLIB)
                printf '\x00\x06\x00\x02\x00\x07\x00\x1c\x01\x02\x00\x01\x00\x01\x00\x01\x00\x01\x00\x00\x00\x01\x00\x01\x00\x01\x00\x01\x00\x00\x00\x04\x04\x00' > "$outfile"
                ;;
        esac
        next_is_rd=false
        continue
    fi
    case "$arg" in
        -rd) next_is_rd=true ;;
    esac
done
echo "mock klayout (CI stub)"
exit 0
