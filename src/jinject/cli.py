import argparse
import json
import logging
import os
import importlib.metadata
import importlib.resources
import subprocess
import jinja2

logger = logging.getLogger(__name__)


def _build_command_args(args: tuple, kwargs: dict) -> list[str]:
    """Convert positional and keyword arguments into a flat command list.

    Positional args become command tokens in order.
    Keyword args are appended as --key=value flags (or --key for boolean True).
    Boolean False kwargs are omitted entirely.
    """
    cmd: list[str] = [str(a) for a in args]
    for key, value in kwargs.items():
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                cmd.append(flag)
        else:
            cmd.append(f"{flag}={value}")
    return cmd


def shell(*args: str, **kwargs: str) -> str:
    """Execute a command and return its stdout as a stripped string.

    Positional arguments form the command tokens. Keyword arguments are
    appended as --key=value flags (underscores become hyphens).

    Raises subprocess.CalledProcessError on non-zero exit.

    Examples (from Jinja):
        {{ shell("echo", "hello") }}
        {{ shell("uv", "run", "my_tool", config="/path/to/cfg") }}
    """
    cmd = _build_command_args(args, kwargs)
    logger.debug("shell: executing %s", cmd)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def shell_json(*args: str, **kwargs: str):
    """Execute a command and parse its stdout as JSON.

    Same argument conventions as shell(). Returns the parsed Python object
    (dict, list, str, etc.) for use in templates.

    Raises subprocess.CalledProcessError on non-zero exit.
    Raises json.JSONDecodeError if stdout is not valid JSON.

    Examples (from Jinja):
        {% set data = shell_json("uv", "run", "my_tool", output="json") %}
        {{ data.some_field }}
    """
    raw = shell(*args, **kwargs)
    return json.loads(raw)


class PackageTemplateLoader(jinja2.BaseLoader):
    """Dynamically routes template lookup calls directly to entry point packages."""
    def __init__(self):
        self.providers = {}
        # Discover all registration blocks listed under 'jinject.templates'
        for ep in importlib.metadata.entry_points(group="jinject.templates"):
            # ep.value looks like 'theme_core:templates' -> split package and subfolder
            pkg, _, resource_dir = ep.value.partition(":")
            self.providers[ep.name] = (pkg, resource_dir or "templates")

    def get_source(self, environment, template):
        # Expects explicit namespacing format: "namespace/file.html"
        if "/" not in template:
            raise jinja2.TemplateNotFound(template)
            
        prefix, _, target_path = template.partition("/")
        if prefix not in self.providers:
            raise jinja2.TemplateNotFound(template)
            
        package_name, base_dir = self.providers[prefix]
        full_resource_path = f"{base_dir}/{target_path}"
        
        try:
            # Safely stream asset records directly out of the target package distribution
            ref = importlib.resources.files(package_name).joinpath(full_resource_path)
            if not ref.is_file():
                raise jinja2.TemplateNotFound(template)
                
            source = ref.read_text(encoding="utf-8")
            return source, None, lambda: True
        except Exception:
            raise jinja2.TemplateNotFound(template)


def _build_env_path_loader() -> jinja2.BaseLoader | None:
    """Build a PrefixLoader from the JINJECT_TEMPLATE_PATH environment variable.

    Each entry on the path (separated by os.pathsep) takes one of two forms:

      namespace=/absolute/path/to/templates
        Registers the directory under the given namespace explicitly.

      /absolute/path/to/directory
        Uses the directory's basename as the namespace.

    Returns None if the variable is unset/empty or yields no valid directories.
    """
    raw = os.environ.get("JINJECT_TEMPLATE_PATH", "")
    if not raw:
        return None

    mapping: dict[str, jinja2.FileSystemLoader] = {}

    for entry in raw.split(os.pathsep):
        entry = entry.strip()
        if not entry:
            continue

        # Determine namespace and directory
        if "=" in entry:
            namespace, _, directory = entry.partition("=")
            namespace = namespace.strip()
            directory = directory.strip()
        else:
            directory = entry
            namespace = os.path.basename(directory.rstrip(os.sep))

        if not namespace:
            logger.debug("Skipping JINJECT_TEMPLATE_PATH entry with empty namespace: %s", entry)
            continue

        if not os.path.isdir(directory):
            logger.debug("Skipping JINJECT_TEMPLATE_PATH entry (not a directory): %s", directory)
            continue

        # Later entries for the same namespace are ignored (first wins)
        if namespace not in mapping:
            mapping[namespace] = jinja2.FileSystemLoader(directory)
            logger.debug("JINJECT_TEMPLATE_PATH: registered namespace '%s' -> %s", namespace, directory)

    if not mapping:
        return None

    return jinja2.PrefixLoader(mapping, delimiter="/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicit Entry-Point Jinja Preprocessor")
    parser.add_argument("input", help="Path to the primary local Jinja layout template.")
    parser.add_argument("-o", "--output", required=True, help="Destination payload filepath.")
    parser.add_argument("-v", "--var", action="append", default=[], help="Variables in key=value format.")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        raise FileNotFoundError(f"Source file not found: {args.input}")

    context = {}
    for var in args.var:
        if "=" in var:
            key, value = var.split("=", 1)
            context[key.strip()] = value.strip()

    # Absolute path execution bound entirely to immediate compilation target directory
    local_dir = os.path.dirname(os.path.abspath(args.input))
    
    # Build loader chain: local files > env-path namespaces > entry-point packages
    loaders: list[jinja2.BaseLoader] = [jinja2.FileSystemLoader(local_dir)]

    env_loader = _build_env_path_loader()
    if env_loader is not None:
        loaders.append(env_loader)

    loaders.append(PackageTemplateLoader())

    env = jinja2.Environment(
        loader=jinja2.ChoiceLoader(loaders),
        trim_blocks=True,
        lstrip_blocks=True
    )

    # Register built-in shell execution globals
    env.globals["shell"] = shell
    env.globals["shell_json"] = shell_json
    
    # Track core extensions and strictly namespace them by their actual package name
    for ep in importlib.metadata.entry_points(group="jinject.plugins"):
        pkg_name = ep.dist.name  # Extracts the source package name, e.g., 'theme_core'
        
        # Ensure the package has its own sub-dictionary namespace in globals
        if pkg_name not in env.globals:
            env.globals[pkg_name] = {}
            
        # Bind the function to its declared entry point key inside that package block
        env.globals[pkg_name][ep.name] = ep.load()

    template_filename = os.path.basename(args.input)
    template = env.get_template(template_filename)
    rendered_content = template.render(**context)

    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)

    with open(args.output, "w") as f:
        f.write(rendered_content)