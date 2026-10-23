from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DATABASE_PATH = PROJECT_ROOT / "database" / "esg_tracker.db"
SCHEMA_PATH = PROJECT_ROOT / "database" / "schema.sql"
CONFIG_DIR = PROJECT_ROOT / "config"

