# The development shell `.envrc` loads: clone, cd, `direnv allow`, and
# bazelisk is on PATH. See README.md, "Optional: nix and direnv".
#
# bazel-orfs needs nothing from the host beyond a standard Linux layout
# (//:host_tools enforces it; the C++ and Python toolchains are hermetic),
# so on Ubuntu, Debian, Fedora and the like bazelisk runs directly against
# the host's /bin and /usr. Where that layout is missing, NixOS for one,
# bazelisk runs in a bubblewrap FHS that supplies it. The check is made on
# every call, never asked: the FHS needs unprivileged user namespaces,
# which Ubuntu's AppArmor and most containers deny, so it is used only
# where it is the only way.
{sources ? import ./npins}: let
  pkgs = import sources.nixpkgs {};

  # What a bazel action and a repository rule reach on a standard Linux:
  # --incompatible_strict_action_env pins an action's PATH to
  # /bin:/usr/bin:/usr/local/bin, which the FHS assembles from this list.
  # Keep it to the tools //:host_tools allows.
  fhs = pkgs.buildFHSEnv {
    name = "bazel-orfs-fhs";
    runScript = pkgs.writeShellScript "bazel-orfs-fhs-entry" ''
      export BAZEL_ORFS_IN_FHS=1
      if [ "$#" -eq 0 ]; then
        exec bash
      fi
      exec -- "$@"
    '';
    targetPkgs = pkgs:
      with pkgs; [
        bash
        coreutils
        diffutils
        file
        findutils
        gawk
        git
        gnugrep
        gnupatch
        gnused
        gnutar
        gzip
        hostname
        curl
        procps
        python3
        which
        # libstdc++ and libz for prebuilt binaries a repository fetches.
        stdenv.cc.cc.lib
        zlib
      ];
    # Ubuntu's per-certificate /etc/ssl/certs links point into the host /usr,
    # which the FHS root replaces; the bundle is a regular file and survives.
    #
    # Test the file rather than the variable: `nix-shell --pure` exports
    # SSL_CERT_FILE=/no-cert-file.crt, which is set and names nothing.
    # nixpkgs' OpenSSL reads NIX_SSL_CERT_FILE first, and --pure poisons that
    # one too: fixing only the first leaves curl working and python failing.
    profile = ''
      if [ ! -r "''${SSL_CERT_FILE:-}" ]; then
        export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
      fi
      if [ ! -r "''${NIX_SSL_CERT_FILE:-}" ]; then
        export NIX_SSL_CERT_FILE="$SSL_CERT_FILE"
      fi
    '';
    # The bazel server must outlive the client invocation that started it.
    dieWithParent = false;
    # nixpkgs' glibc searches /run/current-system/sw/bin first when PATH is
    # unset, and bazel actions run without PATH. On NixOS ORFS's
    # `SHELL := /usr/bin/env bash` then finds the host's bash, whose default
    # PATH is /no-such-path, and its recipes cannot find coreutils.
    extraBwrapArgs = [
      "$([ -d /run/current-system/sw/bin ] && echo --tmpfs \"$(readlink -f /run/current-system/sw/bin)\")"
    ];
  };

  loader =
    if pkgs.stdenv.hostPlatform.isAarch64
    then "/lib/ld-linux-aarch64.so.1"
    else "/lib64/ld-linux-x86-64.so.2";

  # Runs a command against the host when it has a standard Linux layout,
  # in the FHS otherwise. BAZEL_ORFS_FHS=1 or 0 forces the choice.
  mkHostCommand = name: command:
    pkgs.writeShellScriptBin name ''
      fhs="''${BAZEL_ORFS_FHS:-}"
      if [ -z "$fhs" ]; then
        fhs=0
        for f in /bin/bash /usr/bin/env /usr/bin/python3 ${loader}; do
          [ -e "$f" ] || fhs=1
        done
      fi
      if [ "$fhs" = 1 ] && [ -z "''${BAZEL_ORFS_IN_FHS:-}" ]; then
        exec ${fhs}/bin/bazel-orfs-fhs ${command} "$@"
      fi
      exec ${command} "$@"
    '';
in
  if !pkgs.stdenv.hostPlatform.isLinux
  then throw "bazel-orfs builds on Linux only; this shell does not support ${pkgs.stdenv.hostPlatform.system}"
  else
    pkgs.mkShellNoCC {
      packages = [
        (mkHostCommand "bazelisk" "${pkgs.bazelisk}/bin/bazelisk")
        (mkHostCommand "bazel" "${pkgs.bazelisk}/bin/bazelisk")
      ];
      # nixpkgs exports PYTHONPATH for its python packages; bazel's hermetic
      # interpreter would pick it up.
      shellHook = ''
        unset PYTHONPATH
      '';
    }
