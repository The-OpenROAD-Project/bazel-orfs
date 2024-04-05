#!/usr/bin/env bash

set -ex
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

WORKSPACE_ROOT=$(pwd)/../..
WORKSPACE_EXECROOT=$(pwd)
WORKSPACE_EXTERNAL=$WORKSPACE_ROOT/external

XSOCK=/tmp/.X11-unix
XAUTH=/tmp/.docker.xauth
xauth nlist :0 | sed -e 's/^..../ffff/' | xauth -f $XAUTH nmerge -
ARGUMENTS=$@

if test -t 0; then
    DOCKER_INTERACTIVE=-ti
fi

export FLOW_HOME="/OpenROAD-flow-scripts/flow/"
# Get path to the bazel workspace
# Take first symlink from the workspace, follow it and fetch the directory name
export WORKSPACE_ORIGIN=$(dirname $(find $WORKSPACE_EXECROOT -maxdepth 1 -type l -exec realpath {} \; -quit))

# Assume that when docker flow is called from external repository,
# the path to dependencies from bazel-orfs workspace will start with "external".
# Take that into account and construct correct absolute paths.
if [[ $MAKE_PATTERN = external* ]]
then
	export PATH_PREFIX=$WORKSPACE_ROOT
else
	export PATH_PREFIX=$WORKSPACE_EXECROOT
fi

export MAKE_PATTERN_PREFIXED=$PATH_PREFIX/$MAKE_PATTERN

# Prefix MOCK_AREA_TCL if exists
if [[ -n "${MOCK_AREA_TCL}" ]]
then
	export MOCK_AREA_TCL_PREFIXED=$PATH_PREFIX/$MOCK_AREA_TCL
fi

# Configs are always generated in execroot because they are generated in
# the repository that uses bazel-orfs as dependency or in bazel-orfs itself
export DESIGN_CONFIG_PREFIXED=$WORKSPACE_EXECROOT/$DESIGN_CONFIG
export STAGE_CONFIG_PREFIXED=$WORKSPACE_EXECROOT/$STAGE_CONFIG

# Most of these options below has to do with allowing to
# run the OpenROAD GUI from within Docker.
docker run --rm -u $(id -u ${USER}):$(id -g ${USER}) \
 -e LIBGL_ALWAYS_SOFTWARE=1 \
 -e "QT_X11_NO_MITSHM=1" \
 -e XDG_RUNTIME_DIR=/tmp/xdg-run \
 -e DISPLAY=$DISPLAY \
 -e QT_XKB_CONFIG_ROOT=/usr/share/X11/xkb \
 -v $XSOCK:$XSOCK \
 -v $XAUTH:$XAUTH \
 -e XAUTHORITY=$XAUTH \
 -e BUILD_DIR=$WORKSPACE_EXECROOT \
 -e FLOW_HOME=$FLOW_HOME \
 -e DESIGN_CONFIG=$DESIGN_CONFIG_PREFIXED \
 -e STAGE_CONFIG=$STAGE_CONFIG_PREFIXED \
 -e MAKE_PATTERN=$MAKE_PATTERN_PREFIXED \
 -e MOCK_AREA_TCL=$MOCK_AREA_TCL_PREFIXED \
 -e WORK_HOME=$WORKSPACE_EXECROOT/$RULEDIR \
 -v $WORKSPACE_ROOT:$WORKSPACE_ROOT \
 -v $WORKSPACE_ORIGIN:$WORKSPACE_ORIGIN \
 --network host \
 $DOCKER_INTERACTIVE \
 $DOCKER_ARGS \
 ${OR_IMAGE:-openroad/flow-ubuntu22.04-builder:latest} \
 bash -c \
 "set -ex
 . ./env.sh
 cd \$FLOW_HOME
 $ARGUMENTS
 "
