#!/bin/bash
# sink_registers.py on three toys, each checked against its original by a
# 12-cycle miter from reset, with a copy fed the wrong next state as the
# negative control that must fail:
#   sink_toy.sv   a module whose output bundle is a mux of registers, one
#                 inside a submodule, read by two sibling consumers
#   sink_toy2.sv  the registers two levels below the parent, one in the
#                 middle module itself, read by the parent's own logic
#                 (Rob's state, read by CtrlBlock's decode buffer)
#   sink_toy3.sv  the source behind a middle module, the consumers its
#                 siblings (CtrlBlock in Backend, Frontend in XSCore)
#   sink_toy4.sv  the registers two levels down in a module instanced twice
#                 (MemBlock's load units), the consumer's ports matched by
#                 wiring rather than name
set -euo pipefail
YOSYS=$1 SLANG=$2 SINK=$3 TOY=$4 TOY2=$5 TOY3=$6 TOY4=$7
W=${TEST_TMPDIR:-$(mktemp -d)}

miter() { # gold gate top
  $YOSYS -q -m $SLANG -p "
read_slang --top $3 $1; hierarchy -top $3; proc; flatten; rename $3 gold; design -stash g;
read_slang --top $3 $2; hierarchy -top $3; proc; flatten; rename $3 gate; design -stash t;
design -copy-from g gold; design -copy-from t gate;
miter -equiv -flatten -make_assert gold gate miter; hierarchy -top miter; async2sync;
sat -verify -prove-asserts -set-init-zero -seq 12 miter" > $W/miter.log 2>&1
}

check() { # name toy top in-stage good bad -- sink args
  local name=$1 toy=$2 top=$3 stage=$4 good=$5 bad=$6
  shift 7
  mkdir -p $W/$name
  $SINK "$@" --yosys $YOSYS --slang $SLANG --work $W/$name $toy $W/$name/sunk.sv
  python3 - $W/$name/sunk.sv $W/$name/broken.sv "$stage" "$good" "$bad" <<'PY'
import sys
s = open(sys.argv[1]).read()
i = s.index(sys.argv[3])
j = s.index(sys.argv[4], i)
open(sys.argv[2], "w").write(s[:j] + sys.argv[5] + s[j + len(sys.argv[4]):])
PY
  miter $toy $W/$name/sunk.sv $top || { echo "FAIL: $name is not equivalent"; tail -20 $W/miter.log; exit 1; }
  if miter $toy $W/$name/broken.sv $top; then echo "FAIL: $name's negative control passed"; exit 1; fi
}

check flat $TOY Top "Dst d2" ".sink_v_D (_src_sink_v_D)" ".sink_v_D (_src_sink_v_ALOAD)" -- \
  --module Src --flatten Gen --ports io_flush_ --parent Top --instance src --consumers d1=in_flush_,d2=in_flush_
check self $TOY2 P "Mid_sink mid_sink" ".sink_ok (_m_sink_ok)" ".sink_ok (_m_sink_u_st_ALOAD)" -- \
  --module Mid --flatten Leaf --registers u.st --hier --parent P --instance m --consumers self
check path $TOY3 Top "Dst d2" ".sink_v_D (_back_sink_v_D)" ".sink_v_D (_back_sink_v_ALOAD)" -- \
  --module Src --flatten Gen --ports io_flush_ --hier --parent Top --instance back/src --consumers d1=in_flush_,d2=in_flush_
check depth $TOY4 Top "Dst d (" ".sink_u1_s_pipeOutValid_D (_src_sink_u1_s_pipeOutValid_D)" ".sink_u1_s_pipeOutValid_D (_src_sink_u0_s_pipeOutValid_D)" -- \
  --module Src --flatten Unit,Stage --registers u0.s.pipeOutValid,u1.s.pipeOutValid --hier --parent Top --instance src --consumers d=@
echo PASS
