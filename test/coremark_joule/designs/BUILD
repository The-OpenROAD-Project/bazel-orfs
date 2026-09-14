# Root of this study's config.mk designs.
#
# MODULE.bazel points a third orfs_designs() instance at this file. The
# repository rule parses every config.mk under <platform>/ here exactly
# as it parses ORFS's, so these designs get the same generated flow
# targets -- and the same _auto_floorplan_data / _auto_floorplan_pin
# derivation -- without the study having to patch an ORFS checkout.
exports_files(["BUILD"])
