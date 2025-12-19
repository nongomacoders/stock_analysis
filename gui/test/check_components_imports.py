import os
import sys
import pkgutil
import importlib

# Ensure the gui/ directory is on the import path when running this script
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import components

errors = []
for m in pkgutil.iter_modules(components.__path__):
    modname = 'components.' + m.name
    try:
        importlib.import_module(modname)
        print('imported', modname)
    except Exception as e:
        print('FAILED', modname, e)
        errors.append((modname, str(e)))

if errors:
    raise SystemExit(f"Import problems: {len(errors)} modules failed to import")
print('All components imported')
