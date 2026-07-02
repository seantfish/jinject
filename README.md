# jinject

`jinject` is a Jinja2 layout preprocessor designed to enable inclusion of templates with Python packages and dynamic injection of Python utility functions at runtime.

## Installation

In order to use `jinject` with compatible installed system packages, you can run:
```
uv tool install ./jinject
```
This works well for packages installed with `--break-system-packages` or otherwise added to your base path (such as with a `source` command).


## Creating Jinjectable Packages

To register a reusable library function with `jinject`, expose an entry point under the `jinject.plugins` namespace in your asset container package.

### Registering template directories
Templates must be in a directory declared as an entry point and configured to be bundled in the package.

```toml
[project.entry-points."jinject.templates"]
core_layouts = "my_asset_package:templates"

# Hatchling configuration for bundling non-Python assets
[tool.hatch.build.targets.wheel]
packages = ["src/my_asset_package"]
```

### Registering functions
Functions must behave as pure interfaces—accepting standard primitives (`str`, `int`, `float`) and returning structures Jinja can cleanly unpack (such as a generic `dict`).

```python
# located inside: my_asset_package/core.py
def metadata_combiner(prefix: str, count: int) -> dict:
    """Computes layout tag strings and parity flags."""
    return {
        "id_tag": f"{prefix}_{count}",
        "is_even": count % 2 == 0
    }
```

#### Register the Entry Point
Map the python method path within the distribution `pyproject.toml` configuration block:

```toml
[project.entry-points."jinject.plugins"]
get_meta = "my_asset_package.core:metadata_combiner"
```

`jinject` automatically wires `get_meta()` into the global execution block, making it instantly executable within layout templates:

```text
{# Inside template context #}
{% set layout_state = get_meta("node", 4) %}
<div id="{{ layout_state.id_tag }}">Parity Event Status: {{ layout_state.is_even }}</div>
```


## Background

This package was initially created to enable the creation of parameterized worlds for Gazebo. The workflow involves creating a ROS 2 package for Gazebo worlds defined as jinja templates, which themselves contain references to jinja macros from other packages which may define assets. The asset packages contain SDF jinja templates for the assets themselves, capable of taking in parameters and passing them into functions within the package, which could further enable parameterization by for example generating customized meshes.

