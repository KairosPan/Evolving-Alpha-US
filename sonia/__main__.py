from __future__ import annotations

import os


def main() -> None:
    import uvicorn
    host = os.environ.get("ALPHA_SONIA_HOST", "127.0.0.1")
    port = int(os.environ.get("ALPHA_SONIA_PORT", "8810"))
    uvicorn.run("sonia.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
