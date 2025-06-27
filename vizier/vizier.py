# load results from previous runs(possibly empty)
# and suggest new runs for ORFS using Vizier.
import os
import json
import sys
from vizier.service import clients
from vizier.service import pyvizier as vz

def generate_runs(sweep, results, run):
    with open(sweep, "r") as f:
        sweep_config = json.load(f)

    if os.path.exists(results) and os.path.getsize(results) > 0:
        with open(results, "r") as f:
            previous_results = json.load(f)
    else:
        previous_results = {}

    # load autotuner.json and convert it to a Vizier study
    with open(sweep, "r") as f:
        sweep_config = json.load(f)
    
    study_config = vz.StudyConfig(algorithm='DEFAULT')
    for param, value in sweep_config.items():
        if not isinstance(value, dict) or not hasattr(value, 'type'):
            continue
        t = value['type']
        if t == 'int':
            study_config.search_space.root.add_int_param(
                name=param,
                min_value=value['minmax'][0],
                max_value=value['minmax'][1])
        elif t == 'float':
            study_config.search_space.root.add_float_param(
                name=param,
                min_value=value['minmax'][0],
                max_value=value['minmax'][1])
        else:
            raise ValueError(f"Unsupported parameter type: {t}")

    study_config.metric_information.append(
        vz.MetricInformation('clock_period', goal=vz.ObjectiveMetricGoal.MINIMIZE))

    study = clients.Study.from_study_config(study_config,
                                             owner='my_name',
                                             study_id='example')

    # Add previous results to the study
    for result in previous_results:
        study_config.add_measurement(result)

    # Suggest new runs based on the current state of the study
    new_runs = study_config.suggest(1)  # Suggest one new run

    # Save the new runs to the specified file
    with open(run, "w") as f:
        json.dump(new_runs, f, indent=2)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python vizier.py <sweep_config.json> <results.json> <new_runs.json>")
        sys.exit(1)
    generate_runs(*sys.argv[1:4])
