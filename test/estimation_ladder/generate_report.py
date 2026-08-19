import argparse

def parse_yaml(fpath):
    data = {}
    with open(fpath, 'r') as f:
        for line in f:
            if ':' in line:
                k, v = line.split(':', 1)
                data[k.strip()] = v.strip()
    return data

def main():
    parser = argparse.ArgumentParser(description="Generate a report from estimation ladder trends.")
    parser.add_argument("yaml_files", nargs="+", help="Ordered list of estimation YAML files")
    parser.add_argument("--output-report", required=True, help="Path to write the markdown report")
    args = parser.parse_args()

    results = []
    for fpath in args.yaml_files:
        results.append(parse_yaml(fpath))

    with open(args.output_report, 'w') as f:
        f.write("# Estimation Ladder Report\n\n")
        f.write("| Stage | Estimated Min Clock Period (ps) |\n")
        f.write("| --- | --- |\n")
        for res in results:
            period = float(res.get("clock_period", 0.0))
            f.write(f"| {res.get('stage', 'unknown')} | {period:.2f} |\n")

if __name__ == "__main__":
    main()
