#!/bin/bash

set -ex

# Test local build with submacros
target_name=${TARGET:-"L1MetadataArray"}
if [[ -z "$STAGES" ]]; then
  # Skip "grt" "route", takes too long
  STAGES=("synth" "floorplan" "place" "cts")
else
  eval "STAGES=($STAGES)"
fi


if [[ "$target_name" == "L1MetadataArray" || "$target_name" == "subpackage:L1MetadataArray" || "$target_name" == "//sram:top_mix" ]]; then
  macro="true"
fi
echo "Build ${target_name} macro"
for stage in "${STAGES[@]}"
do
  rm -rf ./build
  if [[ -z $SKIP_BUILD ]] ; then
    echo "[${target_name}] ${stage}: Query dependency target"
    bazel query "${target_name}_${stage}_deps"
    bazel query "${target_name}_${stage}_deps" --output=build
    echo "[${target_name}] ${stage}: Build dependency"
    bazel run --subcommands --verbose_failures --sandbox_debug "${target_name}_${stage}_deps" -- "$(pwd)/build"
  fi
  if [[ -z $SKIP_RUN ]] ; then
    stages=()
    if [[ $stage == "synth" ]]; then
        stages+=("do-yosys-canonicalize")
        stages+=("do-yosys")
        stages+=("do-1_synth")
    elif [[ $stage == "grt" ]]; then
        stages+=("do-5_1_grt")
    elif [[ $stage == "route" ]]; then
        stages+=("do-5_2_route")
        stages+=("do-5_3_fillcell")
    elif [[ $stage == "cts" ]]; then
        stages+=("do-cts")
        [ $(find build/_main ! -regex '.*/\(objects\|external\|test\)/.*' -regex '.*\.odb' | wc -l) -eq 1 ]
        [ $(find build/_main ! -regex '.*/\(objects\|external\|test\)/.*' -regex '.*\.sdc' | wc -l) -eq 1 ]
        [ $(find build/_main ! -regex '.*/\(objects\|external\|test\)/.*' -regex '.*\.v' | wc -l) -eq 0 ]
    else
        stages+=("do-${stage}")
    fi
    if [[ "$macro" == "true" ]]; then
      [ $(find build/_main ! -regex '.*/\(objects\|external\|test\)/.*' -regex '.*\.lef' | wc -l) -eq 1 ]
      [ $(find build/_main ! -regex '.*/\(objects\|external\|test\)/.*' -regex '.*\.lib' | wc -l) -eq 1 ]
    fi
    for local_stage in "${stages[@]}"
    do
        echo "[${target_name}] ${local_stage}: Run make script"
        build/make "${local_stage}"
    done
    echo "Check that we can load the result"
    build/make OR_ARGS=-exit open_${stage}
  fi
done

if [[ -z $SKIP_BUILD && -z $SKIP_ABSTRACT ]]; then
    echo "query abstract target"
    bazel query "${target_name}_generate_abstract"
    bazel query "${target_name}_generate_abstract" --output=build
    echo "build abstract"
    bazel build --subcommands --verbose_failures --sandbox_debug "${target_name}_generate_abstract"
fi
