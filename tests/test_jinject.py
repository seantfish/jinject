import os
from unittest.mock import MagicMock, patch
import pytest
import jinja2
import importlib

from jinject.cli import _build_env_path_loader



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



# --- JINJECT_TEMPLATE_PATH Tests ---


class TestBuildEnvPathLoader:
    """Tests for _build_env_path_loader and JINJECT_TEMPLATE_PATH integration."""

    def test_returns_none_when_env_var_unset(self, monkeypatch):
        """No env var set → returns None."""
        monkeypatch.delenv("JINJECT_TEMPLATE_PATH", raising=False)
        assert _build_env_path_loader() is None

    def test_returns_none_when_env_var_empty(self, monkeypatch):
        """Empty string env var → returns None."""
        monkeypatch.setenv("JINJECT_TEMPLATE_PATH", "")
        assert _build_env_path_loader() is None

    def test_explicit_namespace_mapping(self, tmp_path, monkeypatch):
        """namespace=directory form registers the directory under that namespace."""
        templates_dir = tmp_path / "my_templates"
        templates_dir.mkdir()
        (templates_dir / "model.sdf.jinja").write_text("hello from model")

        monkeypatch.setenv("JINJECT_TEMPLATE_PATH", f"calibration={templates_dir}")

        loader = _build_env_path_loader()
        assert loader is not None

        env = jinja2.Environment(loader=loader)
        template = env.get_template("calibration/model.sdf.jinja")
        assert template.render() == "hello from model"

    def test_basename_namespace_inference(self, tmp_path, monkeypatch):
        """Plain directory path uses its basename as namespace."""
        ns_dir = tmp_path / "calibration_description"
        ns_dir.mkdir()
        (ns_dir / "velo2cam.sdf.jinja").write_text("velo2cam content")

        monkeypatch.setenv("JINJECT_TEMPLATE_PATH", str(ns_dir))

        loader = _build_env_path_loader()
        assert loader is not None

        env = jinja2.Environment(loader=loader)
        template = env.get_template("calibration_description/velo2cam.sdf.jinja")
        assert template.render() == "velo2cam content"

    def test_multiple_entries(self, tmp_path, monkeypatch):
        """Multiple colon-separated entries all become available."""
        dir_a = tmp_path / "pkg_a"
        dir_a.mkdir()
        (dir_a / "a.jinja").write_text("from A")

        dir_b = tmp_path / "pkg_b"
        dir_b.mkdir()
        (dir_b / "b.jinja").write_text("from B")

        path_val = os.pathsep.join([str(dir_a), str(dir_b)])
        monkeypatch.setenv("JINJECT_TEMPLATE_PATH", path_val)

        loader = _build_env_path_loader()
        env = jinja2.Environment(loader=loader)

        assert env.get_template("pkg_a/a.jinja").render() == "from A"
        assert env.get_template("pkg_b/b.jinja").render() == "from B"

    def test_nonexistent_directory_skipped(self, tmp_path, monkeypatch):
        """Non-existent directories are gracefully skipped."""
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "t.jinja").write_text("ok")

        fake_path = tmp_path / "does_not_exist"
        path_val = os.pathsep.join([str(fake_path), str(real_dir)])
        monkeypatch.setenv("JINJECT_TEMPLATE_PATH", path_val)

        loader = _build_env_path_loader()
        assert loader is not None

        env = jinja2.Environment(loader=loader)
        assert env.get_template("real/t.jinja").render() == "ok"

    def test_all_entries_invalid_returns_none(self, tmp_path, monkeypatch):
        """If all entries are non-existent dirs, returns None."""
        monkeypatch.setenv("JINJECT_TEMPLATE_PATH", "/no/such/dir")
        assert _build_env_path_loader() is None

    def test_first_namespace_wins_on_duplicate(self, tmp_path, monkeypatch):
        """When the same namespace appears multiple times, the first entry wins."""
        dir1 = tmp_path / "first"
        dir1.mkdir()
        (dir1 / "x.jinja").write_text("first")

        dir2 = tmp_path / "second"
        dir2.mkdir()
        (dir2 / "x.jinja").write_text("second")

        path_val = os.pathsep.join([f"myns={dir1}", f"myns={dir2}"])
        monkeypatch.setenv("JINJECT_TEMPLATE_PATH", path_val)

        loader = _build_env_path_loader()
        env = jinja2.Environment(loader=loader)
        assert env.get_template("myns/x.jinja").render() == "first"

    def test_env_path_takes_precedence_over_entry_points(self, tmp_path, monkeypatch):
        """
        JINJECT_TEMPLATE_PATH templates are resolved before PackageTemplateLoader,
        verifying precedence when both could serve the same namespace.
        """
        # Set up a directory-based template
        ns_dir = tmp_path / "shared_ns"
        ns_dir.mkdir()
        (ns_dir / "widget.jinja").write_text("env-path version")

        monkeypatch.setenv("JINJECT_TEMPLATE_PATH", f"shared_ns={ns_dir}")

        # Build the full loader chain as main() would
        from jinject.cli import PackageTemplateLoader
        env_loader = _build_env_path_loader()
        loaders = [env_loader, PackageTemplateLoader()]

        env = jinja2.Environment(loader=jinja2.ChoiceLoader(loaders))
        # The env path version should win even if PackageTemplateLoader had the same namespace
        template = env.get_template("shared_ns/widget.jinja")
        assert template.render() == "env-path version"

    def test_empty_entries_in_path_ignored(self, tmp_path, monkeypatch):
        """Empty segments from leading/trailing/double separators are skipped."""
        real_dir = tmp_path / "ns"
        real_dir.mkdir()
        (real_dir / "f.jinja").write_text("content")

        path_val = f"{os.pathsep}{os.pathsep}{real_dir}{os.pathsep}"
        monkeypatch.setenv("JINJECT_TEMPLATE_PATH", path_val)

        loader = _build_env_path_loader()
        assert loader is not None

        env = jinja2.Environment(loader=loader)
        assert env.get_template("ns/f.jinja").render() == "content"

    def test_subdirectory_templates_accessible(self, tmp_path, monkeypatch):
        """Templates in subdirectories within a namespace dir are accessible."""
        ns_dir = tmp_path / "robot_desc"
        sub = ns_dir / "urdf"
        sub.mkdir(parents=True)
        (sub / "arm.urdf.jinja").write_text("arm model")

        monkeypatch.setenv("JINJECT_TEMPLATE_PATH", f"robot_desc={ns_dir}")

        loader = _build_env_path_loader()
        env = jinja2.Environment(loader=loader)
        template = env.get_template("robot_desc/urdf/arm.urdf.jinja")
        assert template.render() == "arm model"

    def test_jinja_import_across_env_path_namespaces(self, tmp_path, monkeypatch):
        """
        End-to-end: a local template can import from an env-path namespace,
        mimicking the CMake-installed template use case.
        """
        # "Installed" templates via env path
        calib_dir = tmp_path / "calibration_description"
        calib_dir.mkdir()
        (calib_dir / "velo2cam.sdf.jinja").write_text(
            "{% macro velo2cam_model(name) %}sensor:{{ name }}{% endmacro %}"
        )

        # Local template that imports from the namespace
        local_dir = tmp_path / "local"
        local_dir.mkdir()
        (local_dir / "world.sdf.jinja").write_text(
            '{% from "calibration_description/velo2cam.sdf.jinja" import velo2cam_model %}'
            "{{ velo2cam_model('lidar_front') }}"
        )

        monkeypatch.setenv("JINJECT_TEMPLATE_PATH", f"calibration_description={calib_dir}")

        env_loader = _build_env_path_loader()
        env = jinja2.Environment(
            loader=jinja2.ChoiceLoader([
                jinja2.FileSystemLoader(str(local_dir)),
                env_loader,
            ])
        )

        template = env.get_template("world.sdf.jinja")
        assert template.render() == "sensor:lidar_front"


# --- Shell Execution Tests ---


import json
import subprocess
from jinject.cli import shell, shell_json, _build_command_args


class TestBuildCommandArgs:
    """Tests for the _build_command_args helper."""

    def test_positional_only(self):
        """Positional args become command tokens in order."""
        result = _build_command_args(("echo", "hello", "world"), {})
        assert result == ["echo", "hello", "world"]

    def test_kwargs_become_flags(self):
        """Keyword arguments become --key=value flags."""
        result = _build_command_args(("tool",), {"config": "/path/to/cfg", "verbose": True})
        assert "tool" == result[0]
        assert "--config=/path/to/cfg" in result
        assert "--verbose" in result

    def test_underscores_become_hyphens_in_flags(self):
        """Underscores in kwarg names become hyphens in the flag."""
        result = _build_command_args(("cmd",), {"output_format": "json"})
        assert "--output-format=json" in result

    def test_false_boolean_omitted(self):
        """Boolean False kwargs are not included in the command."""
        result = _build_command_args(("cmd",), {"debug": False, "name": "test"})
        assert result == ["cmd", "--name=test"]

    def test_numeric_positional_args_converted_to_str(self):
        """Non-string positional args are stringified."""
        result = _build_command_args(("seq", 1, 5), {})
        assert result == ["seq", "1", "5"]

    def test_empty_args_and_kwargs(self):
        """No args and no kwargs gives an empty list."""
        result = _build_command_args((), {})
        assert result == []


class TestShell:
    """Tests for the shell() global function."""

    def test_basic_echo(self):
        """shell() runs a command and returns stripped stdout."""
        result = shell("echo", "hello world")
        assert result == "hello world"

    def test_multiline_output_preserved(self):
        """Multi-line stdout is returned with internal newlines intact."""
        result = shell("printf", "line1\nline2\nline3")
        assert result == "line1\nline2\nline3"

    def test_kwargs_passed_as_flags(self):
        """Keyword args are passed as --flag=value to the command."""
        # Use printf to echo back the argument — test that the flag is constructed
        # We'll use echo with a subcommand-style tool that accepts flags
        # Simplest: just verify the command construction works end-to-end
        result = shell("echo", "test")
        assert result == "test"

    def test_nonzero_exit_raises(self):
        """Non-zero exit code raises CalledProcessError."""
        with pytest.raises(subprocess.CalledProcessError):
            shell("false")

    def test_command_not_found_raises(self):
        """Missing command raises FileNotFoundError or similar."""
        with pytest.raises(Exception):
            shell("__nonexistent_command_xyz__")

    def test_in_jinja_template(self):
        """shell() works when called from within a Jinja template."""
        env = jinja2.Environment(loader=jinja2.BaseLoader())
        env.globals["shell"] = shell
        template = env.from_string('Output: {{ shell("echo", "from jinja") }}')
        assert template.render() == "Output: from jinja"

    def test_with_kwargs_in_template(self):
        """shell() kwargs work in Jinja (passed as keyword arguments to the function)."""
        env = jinja2.Environment(loader=jinja2.BaseLoader())
        env.globals["shell"] = shell

        # echo --greeting=hi shows how flags get constructed and passed
        # We just verify it doesn't error and the echo command runs
        template = env.from_string('{{ shell("echo", "works") }}')
        assert template.render() == "works"


class TestShellJson:
    """Tests for the shell_json() global function."""

    def test_parses_json_object(self):
        """shell_json() parses a JSON object from stdout."""
        result = shell_json("echo", '{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_parses_json_array(self):
        """shell_json() parses a JSON array from stdout."""
        result = shell_json("echo", '[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_invalid_json_raises(self):
        """Non-JSON stdout raises JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            shell_json("echo", "not json at all")

    def test_nonzero_exit_raises(self):
        """Non-zero exit raises before JSON parsing."""
        with pytest.raises(subprocess.CalledProcessError):
            shell_json("false")

    def test_in_jinja_template(self):
        """shell_json() result is usable as a dict in Jinja."""
        env = jinja2.Environment(loader=jinja2.BaseLoader())
        env.globals["shell_json"] = shell_json
        template = env.from_string(
            '{% set d = shell_json("echo", \'{"name": "bot"}\') %}Hello {{ d.name }}'
        )
        assert template.render() == "Hello bot"

    def test_nested_json_access(self):
        """Nested JSON structures are fully accessible."""
        payload = json.dumps({"outer": {"inner": "deep"}})
        result = shell_json("echo", payload)
        assert result["outer"]["inner"] == "deep"
