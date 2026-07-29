import pkgutil
import importlib

# Automatically expose all schemas from submodules at app.schemas level
for _, module_name, _ in pkgutil.walk_packages(__path__):
    mod = importlib.import_module(f"{__name__}.{module_name}")
    for attr in dir(mod):
        if not attr.startswith("_"):
            globals()[attr] = getattr(mod, attr)
