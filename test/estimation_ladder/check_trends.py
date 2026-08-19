import argparse
import sys

def parse_yaml(fpath):
    data = {}
    with open(fpath, 'r') as f:
        for line in f:
            if ':' in line:
                k, v = line.split(':', 1)
                data[k.strip()] = v.strip()
    return data

def main():
    parser = argparse.ArgumentParser(description="Validate estimation ladder trends and generate a report.")
    parser.add_argument("yaml_files", nargs="+", help="Ordered list of estimation YAML files")
    parser.add_argument("--output-report", required=True, help="Path to write the markdown report")
    args = parser.parse_args()

    results = []
    for fpath in args.yaml_files:
        results.append(parse_yaml(fpath))

    tolerance = 5.0
    valid = True
    for i in range(1, len(results)):
        prev = results[i-1]
        curr = results[i]
        
        prev_period = float(prev.get("clock_period", 0.0))
        curr_period = float(curr.get("clock_period", 0.0))
        
        if curr_period < prev_period - tolerance:
            print(f"WARNING: Shape validation failed! Stage {curr['stage']} period ({curr_period}) "
                  f"is unexpectedly much faster than stage {prev['stage']} ({prev_period}).", file=sys.stderr)
            valid = False
            
    if len(results) > 1:
        first_period = float(results[0].get("clock_period", 0.0))
        last_period = float(results[-1].get("clock_period", 0.0))
        if last_period < first_period - tolerance:
            print(f"ERROR: Overall shape validation failed! Final stage period ({last_period}) "
                  f"is faster than initial synth stage ({first_period}).", file=sys.stderr)
            valid = False

    with open(args.output_report, 'w') as f:
        f.write("# Estimation Ladder Report\n\n")
        f.write("| Stage | Estimated Min Clock Period (ps) |\n")
        f.write("| --- | --- |\n")
        for res in results:
            period = float(res.get("clock_period", 0.0))
            f.write(f"| {res.get('stage', 'unknown')} | {period:.2f} |\n")

    if not valid:
        sys.exit(1)

if __name__ == "__main__":
    main()
