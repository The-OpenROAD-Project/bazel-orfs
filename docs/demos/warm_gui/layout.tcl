# aes-block at grt, drawn headless for the demo video: the same design the
# GUI screenshot shows, rendered by the build that makes the video.
source $::env(SCRIPTS_DIR)/open.tcl
save_image -web -width 1600 [file join $::env(WORK_HOME) $::env(OUTPUT)]
