from __future__ import annotations
import os


def main() -> None:
    import uvicorn
    host = os.environ.get("ALPHA_WORKBENCH_HOST", "127.0.0.1")
    port = int(os.environ.get("ALPHA_WORKBENCH_PORT", "8820"))
    uvicorn.run("workbench.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
