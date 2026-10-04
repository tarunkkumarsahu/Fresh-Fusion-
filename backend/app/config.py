from pathlib import Path
import os
import tempfile

BASE_DIR = Path(__file__).resolve().parents[2]
IS_VERCEL = bool(os.getenv("VERCEL"))

# Vercel Functions only allow runtime writes in the ephemeral /tmp filesystem.
RUNTIME_DIR = Path(tempfile.gettempdir()) / "freshfusion" if IS_VERCEL else BASE_DIR
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", RUNTIME_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{RUNTIME_DIR / 'freshfusion.db'}")
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]
