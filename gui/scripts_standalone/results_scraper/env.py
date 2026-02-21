from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Credentials:
    username: str | None
    password: str | None


def load_credentials(script_dir: Path) -> Credentials:
    """Loads OST credentials from a `.env` file located in the project root."""
    load_dotenv(dotenv_path=script_dir.parent.parent / ".env")

    username = os.getenv("OST_USERNAME")
    password = os.getenv("OST_PASSWORD")

    if username and username.startswith("your_"):
        username = None
    if password and password.startswith("your_"):
        password = None

    return Credentials(username=username, password=password)
