import sys
content = open("/home/oyvind/bazel-orfs/patches/rules_chisel_circt.patch").read()
# we can see from the error "Wrong chunk detected near line 134: +)" that there's a malformed unified diff here somewhere, maybe EOF newline missing? Let's check with standard patch tools
