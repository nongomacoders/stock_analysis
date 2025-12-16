from pathlib import Path
import os


def print_tree(start_path: Path, exclude_dirs=None) -> str:
    """
    Return a directory tree using box-drawing characters.
    """
    if exclude_dirs is None:
        exclude_dirs = set()

    start_path = start_path.resolve()
    lines = []

    def _walk(path: Path, prefix: str = ""):
        entries = [
            e for e in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            if e.name not in exclude_dirs
        ]

        for index, entry in enumerate(entries):
            is_last = index == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")

            if entry.is_dir():
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension)

    lines.append(start_path.name)
    _walk(start_path)

    return "\n".join(lines)


if __name__ == "__main__":
    start_dir = Path(
        r"c:\Users\diond\Desktop\Projects\GITHUBPROJECTS\stock_analysis\gui"
    )

    excludes = {
        "__pycache__",
        "results",
        ".git",
        ".idea",
        ".vscode",
    }

    tree_str = print_tree(start_dir, excludes)
    print(tree_str)
