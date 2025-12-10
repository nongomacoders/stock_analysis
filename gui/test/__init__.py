# Test package initializer
# Ensure tests can import the application modules (components, core, modules)
# when running tests from the repository root or the gui folder.
import os
import sys

# Add gui/ directory to sys.path so `components`, `core`, and `modules` act like top-level packages
gui_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if gui_dir not in sys.path:
    sys.path.insert(0, gui_dir)
