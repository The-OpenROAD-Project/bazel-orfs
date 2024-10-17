#!/usr/bin/env python3
import os
import yaml
import sys

try:
    from tabulate import tabulate
except ImportError:

    def tabulate(table_data, headers, tablefmt):
        # Simple mock implementation of tabulate
        output = []
        output.append(" | ".join(headers))
        output.append("-" * len(output[0]))
        for row in table_data:
            output.append(" | ".join(map(str, row)))
        return "\n".join(output)


def read_slack_from_yaml(file_path):
    with open(file_path, "r") as file:
        data = yaml.safe_load(file)
        return data.get("slack", "N/A")


def main():
    if len(sys.argv) < 2:
        print("Usage: python script.py <file1.yaml> <file2.yaml> ...")
        sys.exit(1)

    files = sys.argv[1:]
    table_data = []

    for file in files:
        slack = read_slack_from_yaml(file)
        table_data.append([os.path.splitext(os.path.basename(file))[0], slack])

    headers = ["Filename", "Slack"]
    table = tabulate(table_data, headers, tablefmt="github")
    print(table)


if __name__ == "__main__":
    main()
