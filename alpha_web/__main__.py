"""`python -m alpha_web` — serve the console on http://127.0.0.1:8100 (override with ALPHA_WEB_HOST /
ALPHA_WEB_PORT)."""
from __future__ import annotations

import os


def main() -> None:
    import uvicorn
    host = os.environ.get("ALPHA_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("ALPHA_WEB_PORT", "8100"))
    uvicorn.run("alpha_web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
