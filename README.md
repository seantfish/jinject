# jinject

`jinject` is an agnostic Jinja2 layout preprocessor designed to decouple templates from hardcoded workspace paths and dynamically inject Python utility functions at runtime via system entry points.


### 1. Workspace Path Discovery
When target layout files are processed, `jinject` walks up the directory tree to discover relevant asset footprints. It evaluates both the parent context and immediate subdirectories to automatically append folders named `templates/` to the Jinja search path. This allows modules to share layout pieces or macros across separate packages without absolute tracking:

```text
Current Workspace Root/
├── package_alpha/
│   └── templates/
│       └── utils.jinja       <-- Auto-discovered macro module
└── package_beta/
    └── layout.jinja          <-- Targets this file; imports 'utils.jinja' directly
```

### 2. Runtime Extension Injection
Instead of forcing asset maintainers to bake helper logic directly into core template wrappers, `jinject` utilizes python package metadata to discover utilities. Any package exposing entry points under the `jinject.plugins` group is checked at runtime.

---

## Installation & Environment Set Up

Manage local dependencies and isolate development footprints using `uv`.

### Development Boot Loop

```bash
# Clone and enter repository
git clone https://github.com/seantfish/jinja.git
```


## Creating Dynamic Plugins

To register a reusable library function with `jinject`, expose an entry point under the `jinject.plugins` namespace in your asset container package.

### 1. Define the Python Logic
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

### 2. Register the Entry Point
Map the python method path within the distribution `pyproject.toml` configuration block:

```toml
[project.entry-points."jinject.plugins"]
get_meta = "my_asset_package.core:metadata_combiner"
```

Once installed into the target environment workspace (`uv pip install -e .`), `jinject` automatically wires `get_meta()` into the global execution block, making it instantly executable within layout templates:

```text
{# Inside template context #}
{% set layout_state = get_meta("node", 4) %}
<div id="{{ layout_state.id_tag }}">Parity Event Status: {{ layout_state.is_even }}</div>
```

---

## Test Verification Routine

The testing harness leverages mocked entry configurations and dynamic isolated filesystem allocations to verify engine parameters without mutating system environments.

```bash
# Execute localized system tests 
uv run pytest -v
```

### Fault Isolation Guarantees
The internal plugin ingestion matrix encapsulates individual package initialization. If a corrupted or broken plugin raises an `ImportError` or encounters execution failures, `jinject` logs a warning context block, isolates the fault to preserve system stability, and finishes processing valid dependencies.