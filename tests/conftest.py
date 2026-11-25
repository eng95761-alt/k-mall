import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key-test-secret-key-0123456789")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_kmall.db")
os.environ.setdefault("HTTPS_ONLY", "false")
os.environ.setdefault("ADMIN_USERNAME", "owner")
os.environ.setdefault("ADMIN_PASSWORD", "test-password-123")
os.environ.setdefault("ROUTERS_JSON", "[]")

db_file = Path("test_kmall.db")
if db_file.exists():
    db_file.unlink()
