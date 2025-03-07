puts "pwd: [exec pwd]"
exec find .
puts "cp $::env(OBJECTS_DIR)/lib/merged.lib $::env(OUTPUT)"
exec cp $::env(OBJECTS_DIR)/lib/merged.lib $::env(OUTPUT)
