load("@designs_fixture//:designs.bzl", "design")

package(default_visibility = ["//test:__subpackages__"])

# Shares tiny's DESIGN_NICKNAME; design() must still find this
# directory's own config, not the base's (designs_by_directory_test).
design(
    config = "config.mk",
    visibility = ["//test:__subpackages__"],
)
