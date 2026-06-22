"""alpha_web — the Regime Instrument console.

A local FastAPI + HTMX read-only window onto the co-pilot's evolving mind (doctrine / memory /
skills) and its outputs (a day's DecisionPackage, the HCH-vs-Hexpert verdict). Decision-support
only: it shows, it never trades. Run it with `python -m alpha_web` (needs the `web` extra).
"""

__all__ = ["create_app"]


def create_app():  # lazy import so `python -m alpha_web --help`-style probes don't need fastapi
    from alpha_web.app import create_app as _factory
    return _factory()
