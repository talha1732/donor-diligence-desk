"""Start Donor Diligence Desk: API and web UI on http://127.0.0.1:PORT (default 8000).

Run from the repository root:  python backend/run.py
or from the backend folder:    python run.py
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

HOST = "127.0.0.1"


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def main() -> int:
    if sys.version_info < (3, 11):
        print(f"Python 3.11 or newer is required (this is {sys.version.split()[0]}).")
        return 1
    try:
        import uvicorn

        from app.config import ENV_HELP, FRONTEND_DIST, get_settings, key_source
    except ImportError as exc:
        print(f"A required package is missing ({exc.name}). Install them with:")
        print("    pip install -r backend/requirements.txt")
        return 1

    settings = get_settings()
    port = settings.port
    if not _port_free(HOST, port):
        print(f"Port {port} is already in use, so the app cannot start.")
        print("Stop the other program using it, or pick another port, for example:")
        print("    PORT=8001 python backend/run.py        (macOS / Linux)")
        print("    set PORT=8001 && python backend\\run.py  (Windows)")
        return 1

    from app.main import app

    url = f"http://{HOST}:{port}"
    print("Donor Diligence Desk")
    print(f"  Open {url} in your browser (Ctrl+C to stop).")
    if settings.key_present:
        print(f"  PORTKEY_API_KEY found ({key_source()}). Model: {settings.model_name}.")
    else:
        print("  PORTKEY_API_KEY not found: live runs are disabled.")
        print("  " + ENV_HELP)
    if not (FRONTEND_DIST / "index.html").is_file():
        print("  Note: frontend/dist is missing, so / shows a placeholder page. The API still works.")
    if settings.offline_mode:
        print("  OFFLINE_MODE=1: ProPublica data comes from the local cache only.")
    print(f"  Per-run budget ${settings.run_budget_usd:.2f}, daily cap ${settings.daily_budget_usd:.2f}.")
    sys.stdout.flush()

    uvicorn.run(app, host=HOST, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
