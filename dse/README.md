# Design Space Exploration (DSE) Parameterization with Bazel

This project demonstrates how to use **Bazel build settings** with orfs_flow() `settings` argument to manage design parameters for hardware design space exploration (DSE).

## Use Case

Suppose you want to sweep or optimize parameters such as **core utilization** and **placement density** in your hardware design flow.

This setup allows you to:

- Define parameters as Bazel build settings.
- Map those settings to orfs_flow() `settings` variables
- Disambiguate e.g. `PLACE_DENSITY` when managing many orfs_flow() instantiations.

## How It Works

1. **Define Build Settings**

   Use `string_flag` to declare build settings for each parameter:

   ```python
   string_flag(
       name = "density",
       build_setting_default = "0.5",
   )

   string_flag(
       name = "utilization",
       build_setting_default = "45",
   )
   ```

2. **Use build settings in orfs_flow()**

   ```python
   orfs_flow(
      name = "lb_32x128",
      abstract_stage = "place",
      arguments = {
         "CORE_ASPECT_RATIO": "0.5",
         ...
      },
      settings = {
         "CORE_UTILIZATION": ":utilization",
         "PLACE_DENSITY": ":density",
      },
      ...
   )
   ```

2. **Observe that Settings are used**

   The below prints out the ORFS parameters and we observe that we can override the values on the command line:

   ```sh
   bazelisk run --//dse:utilization0="42" --//dse:density0="0.43" //dse:lb_32x128_0_floorplan_deps /tmp/x print-CORE_UTILIZATION print-PLACE_DENSITY
   ```

   Outputs:

   ```sh
   CORE_UTILIZATION = 42
   PLACE_DENSITY = 0.43
   ```
3. **Observe distribution of parameters to stages**:

   The parameters are only distributed to the relevant stages, so for the synthesis stage, we observe default ORFS values, i.e. we don't have to re-run synthesis when floorplan/place settings change.

   ```sh
   $ bazelisk run --//dse:utilization0="42" --//dse:density0="43" //dse:lb_32x128_0_synth_deps /tmp/x print-CORE_UTILIZATION
   CORE_UTILIZATION =
   PLACE_DENSITY = 0.60
   ```

## Parallelism by Bazel

Bazel handles parallelism more efficiently than Optuna would if we were to instantiate Bazel multiple times as the cost of the Bazel server is paid once and Bazel improves provisioning by not running too many processes at once, it defaults to one action per thread.

Parallelism is achieved by creating a static number of duplicates of the flow and parameters using list comprehensions:

```python
N = 2

[string_flag(
    name = "density{}".format(i),
    build_setting_default = "50",
) for i in range(N)]

[orfs_flow(
    name = "lb_32x128_{}".format(i),
    ...
    # top defaults to 'name' of orfs_flow(), so we need
    # to set it to a fixed top level name.
    top = "lb_32x128",
) for i in range(N)]
```
