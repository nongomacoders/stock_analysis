"""
Run the project's GUI unittests with the `gui` folder on sys.path.

Usage: python gui/run_tests.py

This script ensures `gui` is the root package so tests can import modules
directly under `gui` without needing to prepend paths in test files.
"""
import os
import sys
import argparse
import unittest


def main():
    this_dir = os.path.dirname(__file__)
    parent_dir = os.path.abspath(os.path.join(this_dir, '..'))
    # Make repo-level directory available so `import gui.*` works
    sys.path.insert(0, parent_dir)
    # Make sure our working directory is the repo root (parent of gui) so tests referencing files under gui/ work
    os.chdir(parent_dir)

    # Parse optional args for targeted test selection
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", help="Module or test name to run (eg: gui.test.test_analysis_service or gui.test.test_analysis_service.TestClass.test_method)")
    parser.add_argument("--pattern", help="Discovery pattern to use when discovering tests in gui/test (default: 'test_*.py')", default="test_*.py")
    args = parser.parse_args()

    loader = unittest.TestLoader()
    if args.test:
        # If the user supplied a test or module path, run that exact test
        suite = loader.loadTestsFromName(args.test)
    else:
        # Discover tests under the 'test' directory relative to `gui`
        suite = loader.discover(os.path.join(this_dir, "test"), pattern=args.pattern)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
