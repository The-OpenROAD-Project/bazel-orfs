// netlistsvg is a dependency installed with npm
// call netlistsvg module with the command line arguments
var netlistsvg = require('netlistsvg/bin/netlistsvg.js');

var yargs = require('yargs');

var argv = yargs
.demand(1)
.usage('usage: $0 input_json_file [-o output_svg_file] [--skin skin_file] [--layout elk_json_file]')
.argv;

// print cwd
console.log(process.cwd());

netlistsvg.main(argv._[0], argv.o, argv.skin, argv.layout);
