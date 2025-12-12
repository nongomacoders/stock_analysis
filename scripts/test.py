import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path("scripts") / ".env")
print(os.getenv("OST_PASSWORD"))
print(os.getenv("OST_USERNAME"))
