catch { set_cmd_units -time ns -capacitance pF -current mA -voltage V -resistance kOhm -distance um }
read_db $::env(ODB_FILE)

# Catch reporting commands since they require liberty files to be loaded, 
# which we don't have in this mock test without load.tcl
catch { report_clock_skew }
catch { report_tns }
catch { report_cell_usage }
puts "Mock script completed successfully!"
