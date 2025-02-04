# Test FASTROUTE_TCL 
set_global_routing_layer_adjustment $::env(MIN_ROUTING_LAYER)-$::env(MAX_ROUTING_LAYER) $::env(ROUTING_LAYER_ADJUSTMENT)
set_routing_layers -signal $::env(MIN_ROUTING_LAYER)-$::env(MAX_ROUTING_LAYER)
if {[env_var_exists_and_non_empty MACRO_EXTENSION]} {
  set_macro_extension $::env(MACRO_EXTENSION)
}
  