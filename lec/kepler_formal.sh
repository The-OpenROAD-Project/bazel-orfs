#!/bin/bash
# Wrapper for kepler-formal binary.
# Set KEPLER_FORMAL to override the default path.
KEPLER_FORMAL="${KEPLER_FORMAL:-kepler-formal}"
exec "$KEPLER_FORMAL" "$@"
