#! /bin/sh

set -e

if [ -z "$FLOW_HOME" ]; then
  export YOSYS_CMD={YOSYS_PATH}
  export OPENROAD_EXE={OPENROAD_PATH}
  export KLAYOUT_CMD={KLAYOUT_PATH}
  export FLOW_HOME={MAKEFILE_DIR}
fi

exec make --file "$FLOW_HOME/Makefile" "$@"
