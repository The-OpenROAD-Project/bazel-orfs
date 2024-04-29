#!/usr/bin/env bash

set -ex
uuid=$(uuidgen)

function handle_sigterm() {
	# Wait if container is not created
	if [[ ! "$( docker container inspect -f '{{.State.Status}}' bazel-orfs-$uuid )" =~ ^(running|created)$ ]]; then
		sleep 3s
	fi
	# Stop or remove container
	docker container rm -f "bazel-orfs-$uuid" || true
}

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ $DIR == */external/bazel-orfs~override ]]; then
	WORKSPACE_ROOT=$(realpath $DIR/../../../../../../..)
else
	WORKSPACE_ROOT=$(realpath $DIR/../../../../..)
fi
WORKSPACE_EXECROOT=$WORKSPACE_ROOT/execroot/_main
WORKSPACE_EXTERNAL=$WORKSPACE_ROOT/external

# Automatically mount bazel-orfs directory if it is used as module with local_path_override
if [[ $DIR == */external/bazel-orfs~override ]]; then
	BAZLE_ORFS_DIR=$(realpath $WORKSPACE_ROOT/external/bazel-orfs~override)
	DOCKER_ARGS="$DOCKER_ARGS -v $BAZLE_ORFS_DIR:$BAZLE_ORFS_DIR"
fi

XSOCK=/tmp/.X11-unix
XAUTH=/tmp/.docker.xauth
xauth nlist :0 | sed -e 's/^..../ffff/' | xauth -f $XAUTH nmerge -
ARGUMENTS=$@

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

# Prefix env var if exists
if [[ -n "${MOCK_AREA_TCL}" ]]
then
	MOCK_AREA_TCL_PREFIXED="-e MOCK_AREA_TCL=$PATH_PREFIX/$MOCK_AREA_TCL"
fi
if [[ -n "${MEMORY_DUMP_TCL}" ]]
then
	MEMORY_DUMP_TCL_PREFIXED="-e MEMORY_DUMP_TCL=$PATH_PREFIX/$MEMORY_DUMP_TCL"
fi
if [[ -n "${MEMORY_DUMP_PY}" ]]
then
	MEMORY_DUMP_PY_PREFIXED="-e MEMORY_DUMP_PY=$PATH_PREFIX/$MEMORY_DUMP_PY"
fi

# Configs are always generated in execroot because they are generated in
# the repository that uses bazel-orfs as dependency or in bazel-orfs itself
export DESIGN_CONFIG_PREFIXED=$WORKSPACE_EXECROOT/$DESIGN_CONFIG
export STAGE_CONFIG_PREFIXED=$WORKSPACE_EXECROOT/$STAGE_CONFIG

# Make bazel-bin writable
chmod -R +w $WORKSPACE_EXECROOT/bazel-out/k8-fastbuild/bin

export MAKEFILES=$FLOW_HOME/Makefile

# Handle TERM signals
# this option requires `supports-graceful-termination` tag in Bazel rule
trap handle_sigterm SIGTERM

# Most of these options below has to do with allowing to
# run the OpenROAD GUI from within Docker.
docker run --name "bazel-orfs-$uuid" --rm \
 -u $(id -u ${USER}):$(id -g ${USER}) \
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
 -e MAKEFILES=$MAKEFILES \
 -e DESIGN_CONFIG=$DESIGN_CONFIG_PREFIXED \
 -e STAGE_CONFIG=$STAGE_CONFIG_PREFIXED \
 -e MAKE_PATTERN=$MAKE_PATTERN_PREFIXED \
 -e WORK_HOME=$WORKSPACE_EXECROOT/$RULEDIR \
 $MOCK_AREA_TCL_PREFIXED \
 $MEMORY_DUMP_TCL_PREFIXED \
 $MEMORY_DUMP_PY_PREFIXED \
 -v $WORKSPACE_ROOT:$WORKSPACE_ROOT \
 -v $WORKSPACE_ORIGIN:$WORKSPACE_ORIGIN \
 --network host \
 $DOCKER_INTERACTIVE \
 $DOCKER_ARGS \
 ${OR_IMAGE:-openroad/flow-ubuntu22.04-builder:latest} \
 bash -c \
 "set -ex
 . ./env.sh
 cd \$BUILD_DIR
 $ARGUMENTS
 " &

# Wait for Docker container to finish
# Docker container has to be run in subprocess,
# otherwise signal will not be handled immediately
wait $!
