FROM ubuntu:22.04
SHELL ["/bin/bash", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
ARG USERNAME=root
ARG USER_HOME=/root
ARG ORFS_REF=067099e79f308b77cb7f031f37d2f9ca2ac25b7b

RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install -y sudo git vim wget python-is-python3 && \
    # Setup ORFS under ~
    mkdir -p $USER_HOME && \
    cd $USER_HOME && \
    git clone --recursive https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts && \
    echo "export ORFS=$USER_HOME/OpenROAD-flow-scripts" > $USER_HOME/orfs_path.sh && \
    cd $USER_HOME/OpenROAD-flow-scripts && \
    git checkout $ORFS_REF && \
    export SUDO_USER=$USERNAME && \
    sudo ./setup.sh && \
    ./build_openroad.sh --local && \
    # test ORFS build
    source ./env.sh && yosys -help && openroad -help && cd flow && make -j $(nproc) && \
    # Install bazelisk as bazel
    sudo wget https://github.com/bazelbuild/bazelisk/releases/download/v1.19.0/bazelisk-linux-amd64 -O /usr/local/bin/bazel && \
    sudo chmod +x /usr/local/bin/bazel

WORKDIR $USER_HOME
