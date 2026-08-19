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
    if len(sys.argv) < 2:
        print("Usage: check_trends_test.py <yaml_file1> <yaml_file2> ...")
        sys.exit(1)
        
    yaml_files = sys.argv[1:]
    results = []
    for fpath in yaml_files:
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
            
    if not valid:
        sys.exit(1)
    
    print("Shape validation passed.")

if __name__ == "__main__":
    main()
