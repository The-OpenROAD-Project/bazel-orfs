load("@designs_fixture//:designs.bzl", "design")

# Scoped to test/, not public: public_surface.py refuses a public target
# under test/, and nothing outside this fixture has any business here.
package(default_visibility = ["//test:__subpackages__"])

exports_files(["constraints.sdc"])

# If the tree was not discovered, DESIGNS has no entry for this design
# and design() declares nothing -- which is the silent failure the
# //test/designs_fixture test exists to catch.
design(
    config = "config.mk",
    visibility = ["//test:__subpackages__"],
)
