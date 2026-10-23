from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import initialize_database


if __name__ == "__main__":
    path = initialize_database()
    print(f"SQLite initialized: {path}")
