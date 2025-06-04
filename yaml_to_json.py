# yaml_to_json.py
import yaml
import json
import sys


def yaml_to_json(yaml_file, output_file):
    with open(yaml_file, "r") as f:
        data = yaml.safe_load(f)
    for value in data.values():
        # Reduce size
        del value["description"]

    with open(output_file, "w") as f:
        json.dump(data, f)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: yaml_to_json.py <input_yaml> <output_json>")
        sys.exit(1)

    yaml_to_json(sys.argv[1], sys.argv[2])
