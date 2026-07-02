import argparse
import os
import importlib.metadata
import importlib.resources
import jinja2

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
    
    # Establish engine setup: Fall back to installed entry-point spaces only
    env = jinja2.Environment(
        loader=jinja2.ChoiceLoader([
            jinja2.FileSystemLoader(local_dir),
            PackageTemplateLoader()
        ]),
        trim_blocks=True,
        lstrip_blocks=True
    )
    
    # Track core extensions
    for ep in importlib.metadata.entry_points(group="jinject.plugins"):
        env.globals[ep.name] = ep.load()

    template_filename = os.path.basename(args.input)
    template = env.get_template(template_filename)
    rendered_content = template.render(**context)

    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)

    with open(args.output, "w") as f:
        f.write(rendered_content)