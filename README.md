# jinject

`jinject` is a Jinja2 layout preprocessor designed to enable inclusion of templates with Python packages and dynamic injection of Python utility functions at runtime.

## Installation

In order to use `jinject` with compatible installed system packages, you can run:
```
uv tool install ./jinject
```
This works well for packages installed to your base global environment (such as via `apt`, `pip --break-system-packages`, or a sourced ROS 2 workspace).

## Creating Jinjectable Packages

Packages can expose both templates and executable Python helper macros directly to the `jinject` processor via standard entry points.

### Registering template directories

Templates must reside inside your Python package directory structure (e.g., src/my_asset_package/templates/) and added as a `"jinject.templates"` entry-point. Here is an example of a `pyproject.toml`:

```
[project]
name = "my_asset_package"
version = "1.0.0"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.entry-points."jinject.templates"]
# Maps the prefix "core_layouts/" to the package's templates/ folder
core_layouts = "my_asset_package:templates"

# Ensure Hatchling sweeps up non-Python (e.g. *.jinja) files
[tool.hatch.build.targets.wheel]
packages = ["src/my_asset_package"]

Downstream files can now import these assets explicitly using the defined namespace key:
{% import 'core_layouts/base.html' as theme %}
```


### Registering functions
Functions must behave as pure interfaces—accepting standard primitives (str, int, float) and returning structures Jinja can cleanly process or unpack (such as a generic dict or list or string).
```
# located inside: src/my_asset_package/core.py

def metadata_combiner(prefix: str, count: int) -> dict:
    """Computes layout tag strings and parity flags."""
    return {
        "id_tag": f"{prefix}_{count}",
        "is_even": count % 2 == 0
    }
```
Map this function path under the jinject.plugins entry point namespace inside your pyproject.toml:
```
[project.entry-points."jinject.plugins"]
get_meta = "my_asset_package.core:metadata_combiner"
```

#### Register the Entry Point
Map the python method path within the distribution `pyproject.toml` configuration block:

```toml
[project.entry-points."jinject.plugins"]
get_meta = "my_asset_package.core:metadata_combiner"
```
### Using functions in the template

`jinject` automatically wires `get_meta()` into the global execution block, making it instantly executable within layout templates:

```text
{# Inside template context #}
{% set layout_state = get_meta("node", 4) %}
<div id="{{ layout_state.id_tag }}">Parity Event Status: {{ layout_state.is_even }}</div>
```

## Background

`jinject` was originally created to generate highly parameterized simulation environments for Gazebo. The workflow maps directly to a modular robotic ecosystem:

* World Containers: ROS 2 packages define overall Gazebo world environments as top-level Jinja files.
* Asset Containers: Independent hardware/robot packages bundle parameterized SDF templates alongside python procedural helpers (e.g., generating dynamic collision hulls, specific wheel configurations, or customized meshes).

