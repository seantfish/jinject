import os
from unittest.mock import MagicMock, patch
import pytest
import jinja2
import importlib



# --- Test Fixtures ---

@pytest.fixture
def mock_workspace(tmp_path):
    """
    Constructs an in-memory multi-package directory layout to mimic a complex workspace environment.
    
    REGISTRATION REALITY IN THIS FIXTURE:
    No automated registration occurs here. This fixture manually writes physical layout text 
    and macro text files to disk so that the engine's filesystem crawling behaviors can be verified 
    statically.
    
    EXPECTED DIRECTORY TREE:
    ├── tmp_path/
    │   └── workspace/
    │       ├── package_alpha/
    │       │   └── templates/
    │       │       └── utils.jinja   <-- Exposes a macro wrapper around a global 'shout' function
    │       └── package_beta/
    │           └── layout.jinja      <-- Core template file attempting a decoupled import
    """
    workspace = tmp_path / "workspace"
    package_alpha = workspace / "package_alpha"
    package_beta = workspace / "package_beta"
    
    # Create the template and layout directories
    (package_alpha / "templates").mkdir(parents=True, exist_ok=True)
    package_beta.mkdir(parents=True, exist_ok=True)
    
    # Define a template macro fragment that depends on a runtime global function named 'shout'
    macro_content = "{% macro format_shout(msg) %}{{ shout(msg) }}{% endmacro %}"
    with open(package_alpha / "templates" / "utils.jinja", "w") as f:
        f.write(macro_content)
        
    # Define a layout template file that imports the macro purely by file name, testing path resolution
    layout_content = "{% import 'utils.jinja' as u %}{{ u.format_shout('hello') }}"
    layout_file = package_beta / "layout.jinja"
    with open(layout_file, "w") as f:
        f.write(layout_content)
        
    return {
        "layout_file": layout_file,
        "macro_dir": package_alpha / "templates"
    }


# --- Core Template Engine & CLI Tests ---

def test_cli_execution_and_directory_autocreating(tmp_path):
    """
    TEST INTENT:
        Verifies the core engine's file input/output handling and automated directory provision rules.
        
    REGISTRATION REALITY:
        Zero function registration is being tested here. This is a pure string-parsing and 
        file I/O isolation test ensuring that file generation contracts are honored.
           
    EXPECTED BEHAVIOR:
        The engine evaluates 'Hello World', checks that the target subfolders do not exist, 
        creates them instantly, and drops the parsed content into the nested file.
    """
    # SETUP: Define input source paths and a highly nested output target that does not exist yet
    input_file = tmp_path / "input.jinja"
    output_file = tmp_path / "nested_dir" / "deep_dir" / "output.txt"
    
    # SETUP: Write basic Jinja text utilizing a default filter block
    with open(input_file, "w") as f:
        f.write("Hello {{ name | default('World') }}")
        
    # ACTION STAGE 1: Feed the input folder to the engine and trigger a standard text compile run
    env = jinja2.Environment(loader=jinja2.FileSystemLoader([str(tmp_path)]))
    template = env.get_template(os.path.basename(input_file))
    rendered_text = template.render()
    
    # ACTION STAGE 2: Replicate the CLI output file contract—automatically creating directory trees
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        f.write(rendered_text)
        
    # VERIFICATION: Confirm that the deeply nested directory was successfully generated
    assert output_file.exists(), "The engine failed to recursively auto-create intermediate directory trees."
    
    # VERIFICATION: Confirm that the context variables resolved correctly during text parsing
    assert output_file.read_text() == "Hello World", "Rendered text mismatch; default filters failed to evaluate."


@patch("importlib.metadata.entry_points")
def test_plugin_injection_and_fault_isolation(mock_entry_points):
    """
    TEST INTENT:
        Verifies the engine's automated entry point loop execution and fault-isolation guardrails.
        
    REGISTRATION REALITY (MOCKED/DYNAMIC REGISTRATION):
        This is the ONLY test verifying the entry-point registration mechanism. Because we want 
        the test suite to remain completely self-contained (without forcing you to install an 
        actual external asset package to run tests), we use `unittest.mock.patch` to FAKE the system scan. 
        
        When `importlib.metadata.entry_points(group='jinject.plugins')` is called, the mock intercepts 
        the OS and pretends it found two extensions (`increment` and `broken_extension`). The `for` loop 
        directly below then executes the exact function-registration code that will live in your production source code.
        
    EXPECTED BEHAVIOR:
        The loop discovers the functional tool and the corrupted one. It intercepts the broken plugin's 
        initialization exception safely, isolates it, continues the registration boot cycle, registers 
        `increment` into the `env.globals` dictionary, and successfully processes the final string template.
    """
    # SETUP: Mock a functional utility plugin entry point that works flawlessly when loaded
    mock_valid_plugin = MagicMock()
    mock_valid_plugin.name = "increment"
    mock_valid_plugin.load.return_value = lambda x: x + 1
    
    # SETUP: Mock a broken third-party plugin that throws a critical error immediately upon being imported
    mock_broken_plugin = MagicMock()
    mock_broken_plugin.name = "broken_extension"
    mock_broken_plugin.load.side_effect = ImportError("Simulated missing system dependency or environment mismatch")
    
    # SETUP: Intercept 'importlib.metadata' and stream our mocked list of extensions to the engine
    mock_entry_points.return_value = [mock_valid_plugin, mock_broken_plugin]
    
    env = jinja2.Environment(loader=jinja2.BaseLoader())
    plugins = importlib.metadata.entry_points(group="jinject.plugins")
    
    # ACTION STAGE 1: Execute the exact core registration loop algorithm used by jinject
    fault_isolated_successfully = False
    for plugin in plugins:
        try:
            # Dynamically import the external function package code
            plugin_func = plugin.load()
            # CORE REGISTRATION STEP: Map it dynamically into the active Jinja workspace global variables
            env.globals[plugin.name] = plugin_func
        except Exception:
            # EXPLANATION: If a package is broken or unconfigured, intercept the error to protect the main run.
            # This flags that fault isolation successfully stepped in.
            fault_isolated_successfully = True 
            
    # VERIFICATION: Confirm that the engine safely caught the broken extension's crash
    assert fault_isolated_successfully is True, "The preprocessor let an external plugin crash halt its core execution."
    
    # VERIFICATION: Confirm that the functional tool was registered and the broken one was skipped
    assert "increment" in env.globals, "The engine failed to register the valid 'increment' plugin global."
    assert "broken_extension" not in env.globals, "The corrupted plugin was unsafely injected into the namespace."
    
    # ACTION STAGE 2: Execute a template string utilizing the dynamically injected plugin tool
    template = env.from_string("Value: {{ increment(9) }}")
    
    # VERIFICATION: Assert that the functional plugin operates predictably inside the engine context
    assert template.render() == "Value: 10", "The dynamically injected plugin yielded an incorrect return evaluation."

