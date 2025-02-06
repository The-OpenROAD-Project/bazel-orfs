import yaml
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import os
import sys
import re

# Command-line arguments
if len(sys.argv) < 4:
    raise ValueError("Usage: python script.py <output_pdf> <title> <input_files...>")

output_pdf = sys.argv[1]
output_yaml = sys.argv[2]
output_csv = sys.argv[3]
title = sys.argv[4]
input_files = sys.argv[5:]

# Load data from input files
file_data = {}
for file in input_files:
    with open(file, "r") as f:
        data = yaml.safe_load(f)
        file_data[file] = data

# Group data by series
series_map = defaultdict(list)
for file in input_files:
    name = data["name"]
    match = re.match(r"^(.*?)(\d+)_[a-z]+_stats$", os.path.basename(file))
    if not match:
        raise ValueError(f"Invalid name format: {name}")
    # Quick and dirty way to extract the series name and index
    series = match.group(1).rstrip("_")
    index = int(match.group(2))

    series_map[series].append((index, file_data[file]))

with open(output_yaml, "w") as f:
    yaml.dump({name: dict(points) for name, points in series_map.items()}, f)

# now in csv format with two levels of dicts
with open(output_csv, "w") as f:
    for name, points in series_map.items():
        for index, data in points:
            f.write(
                f"{name},{index},{data['power']},{data['clock_period']},{data['area']}\n"
            )

# Sort and normalize the series by index
normalized_series = {}
normalized_series_x = {}
for name, points in series_map.items():
    points.sort(key=lambda x: x[0])  # Sort by index
    normalized_series_x[name] = list(map(lambda x: x[0], points))
    normalized_series[name] = np.array([p[1] for p in points])


def plot_one(pdf_pages, data_key):
    # Extract the specified series
    series_names = sorted(
        list(normalized_series.keys()),
        reverse=True,
        key=lambda name: max(map(lambda n: n[data_key], normalized_series[name])),
    )
    serieses = list(
        map(
            lambda series_name: np.array(
                list(map(lambda item: item[data_key], normalized_series[series_name]))
            ),
            series_names,
        )
    )

    # Plot the results
    plt.figure(figsize=(8, 5))

    fig, ax1 = plt.subplots()

    # Calculate the ratio (series1_value / series2_value)
    if len(serieses) >= 2:
        ratios = serieses[0] / serieses[1]
        alus = normalized_series_x[series_names[0]]

        # Plot the first series with the left y-axis
        ax1.plot(
            alus,
            ratios,
            marker="o",
            label=f"Ratio ({series_names[0]}/{series_names[1]})",
            color="b",
        )
        ax1.set_ylabel(f"Ratio", color="b")
        ax1.tick_params(axis="y", labelcolor="b")
        ax1.set_ylim(bottom=0)

        # Set x-axis to display only integer values
        ax1.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    ax2 = ax1.twinx()
    for series, series_name in zip(serieses, series_names):
        # sys.exit(1)
        ax2.plot(
            normalized_series_x[series_name],
            series,
            # marker="x",
            label=series_name + " " + data_key,
            # color="g",
        )
    # Set x-axis to display only integer values
    ax2.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax2.set_ylabel(
        data_key
        + "/"
        + {
            "clock_period": "seconds",
            "power": "W",
            "instances": "instances",
            "area": r"$\mathrm{\mu m}^2$",
        }[data_key],
        color="r",
    )
    ax2.set_ylim(bottom=0)
    ax2.tick_params(axis="y", labelcolor="r")

    fig.legend(loc="upper left", bbox_to_anchor=(0.1, 0.9))
    plt.grid(True)
    plt.title(f"{title} - {data_key}")
    plt.tight_layout()
    pdf_pages.savefig(fig)
    plt.close(fig)


with PdfPages(output_pdf) as pdf_pages:
    for data_key in [
        "power",
        "clock_period",
        "area",
    ]:
        plot_one(pdf_pages, data_key)
