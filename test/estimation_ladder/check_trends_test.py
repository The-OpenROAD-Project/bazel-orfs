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
    results = [parse_yaml(f) for f in yaml_files]

    periods = [float(res.get("clock_period", 0.0)) for res in results]
    stages = [res.get("stage", "unknown") for res in results]
    
    if len(periods) == 0:
        print("ERROR: No data to validate.", file=sys.stderr)
        sys.exit(1)
        
    # Check 1: Differentiation Check
    # At least some of the stages should produce different results, proving the ladder does something.
    if len(set(periods)) == 1 and len(periods) > 1:
        print(f"ERROR: All stages produced the exact same clock period ({periods[0]}). Scripts may not be applying physical changes.", file=sys.stderr)
        sys.exit(1)
        
    # Check 2: Sanity / Bounding Check
    # The max variance shouldn't exceed 50% of the max period.
    max_period = max(periods)
    min_period = min(periods)
    
    if max_period <= 0:
        print("ERROR: Maximum clock period is <= 0. Something is very wrong.", file=sys.stderr)
        sys.exit(1)
        
    variance_ratio = (max_period - min_period) / max_period
    
    print("Sanity Check Metrics:")
    for stage, period in zip(stages, periods):
        print(f" - {stage}: {period}")
    print(f"Max Period: {max_period}")
    print(f"Min Period: {min_period}")
    print(f"Variance Ratio: {variance_ratio:.2%}")
    
    if variance_ratio > 0.5:
        print(f"ERROR: Variance between stages ({variance_ratio:.2%}) exceeds 50% threshold. Scripts may be broken.", file=sys.stderr)
        sys.exit(1)
        
    print("Sanity validation passed.")
    sys.exit(0)

if __name__ == "__main__":
    main()
