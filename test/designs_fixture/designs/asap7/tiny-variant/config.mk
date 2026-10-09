# A variant that includes its base design's config.mk, the way ORFS's
# variants do. The base sets DESIGN_NICKNAME after this file could, so
# the two share the nickname "tiny"; only the directory tells them apart.
include designs/asap7/tiny/config.mk

export CORE_UTILIZATION        = 30
