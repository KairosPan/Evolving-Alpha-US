# scripts/serve_web.py
"""本地起 web:python scripts/serve_web.py  → http://127.0.0.1:8000(默认进 /research/harness)。"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("youzi_web.app:app", host="127.0.0.1", port=8000, reload=True)
