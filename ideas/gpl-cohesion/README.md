# Cohesion pull in global placement, XSTile's answer

The material behind ideas/xiangshan-timing.md entry 54's XSTile addendum, kept so the
arm can be run again:

- `openroad-gpl-cohesion.patch`: OpenROAD's `global_placement -clusters_file`.
  Each named group of cells (instance-name prefixes) is pulled toward its own
  centroid, or toward an anchor, with a force scaled to the mean wirelength
  gradient. The force fades as exp(-iter / tau_iter); tau_iter 0 never fades.
  The patch applies to OpenROAD bfac0546.
- `xstile_clusters.json`: the six groups of the measured arm: dispatch, decode,
  rename, memCtrl, the 13 integer issue queues, and fusionDecoder. Weight 1,
  no fade.
- `run.sh`: the dirty lane that measured it, from the parent's floorplan
  through grt and the KPI.

What it measured, and what it leaves open, is in entry 54.
