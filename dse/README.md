# Design Space Exploration (DSE) Parameterization with Bazel

This project demonstrates how to use **Bazel build settings** with orfs_flow() `settings` argument to manage design parameters for hardware design space exploration (DSE).

## Use Case

Suppose you want to sweep or optimize parameters such as **core utilization** and **placement density** in your hardware design flow. This setup allows you to:

- Define parameters as Bazel build settings.
- Map those settings to orfs_flow() `settings` variables
- Disambiguate e.g. `PLACE_DENSITY` when managing many orfs_flow() instantiations.

## How It Works

1. **Define Build Settings**

   Use `string_flag` to declare build settings for each parameter:

   ```python
   string_flag(
       name = "density",
       build_setting_default = "50",
   )

   string_flag(
       name = "utilization",
       build_setting_default = "45",
   )
   ```

2. **Convert Parameters to JSON for Flow Graphs**

   The system converts configuration parameters to a `.json` file that can be fed into a static `orfs_flow()` graph. Each stage in the flow runs an action to whittle the `.json` file down to just the parameters needed for that stage.

   This allows configuring the entire `orfs_flow()` graph directly from the Bazel command line using `--//path:parameter=value` pairs defined by the user.

3. **Map Build Settings to Parameter Names**

   Use a custom `param` rule to map Bazel flags to parameter names:

   ```python
   param(
       name = "params",
       parameters = {
           ":density": "PLACE_DENSITY",
           ":utilization": "CORE_UTILIZATION",
       },
   )
   ```

4. **Build and Export Parameters**

   Build the `params` target with custom values for each parameter:

   ```sh
   bazelisk run --//dse:utilization="42" --//dse:density="43" //dse:lb_32x128_floorplan_deps /tmp/x print-CORE_UTILIZATION print-PLACE_DENSITY
   ```

   Outputs:

   ```sh
   CORE_UTILIZATION = 42
   PLACE_DENSITY = 43
   ```

## Benefits

- **Reproducibility:** All parameter values are tracked by Bazel, ensuring reproducible builds.
- **Automation:** Easily sweep parameters in scripts or optimization loops.
- **Integration:** Exported parameters can be consumed by downstream tools (e.g., synthesis, place-and-route, simulation).
