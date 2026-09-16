# Pins on the top and bottom edges only.
#
# ORFS's own asap7/swerv_wrapper does this, and the reason is visible in
# the floorplan: the three SRAM macros want the left and right of the
# core area, and pins placed there fight them for routing resources on
# the layers the macros already occupy.
#
# Taken as-is rather than re-derived. It is a floorplan hint, not a
# measurement choice -- it changes where things sit, not what is
# measured.
exclude_io_pin_region -region left:* -region right:*
