"""The paper book: a strategy's simulated account, kept by the engine outside the workspace.

``PaperBook`` (book.py) keeps one book — fills, marks, corporate actions, the chained ledger,
``verify``; ``intent`` is the one shape a strategy's ``signal.py`` answers with; ``home`` says
where books live (``ALPHA_PAPER_HOME``, then ``$DSH_HOME/face/paper``). The operator drives it
with ``scripts/paper_book.py``. No order path is imported anywhere under this package.
"""
from alpaca_kit.paper.book import DEFAULT_PARAMS, BookError, PaperBook, Position
from alpaca_kit.paper.home import book_dir, is_strategy_name, paper_home
from alpaca_kit.paper.intent import (
    Intent,
    IntentError,
    Target,
    call_signal,
    load_signal,
    validate_intent,
    wants_holdings,
)

__all__ = [
    "DEFAULT_PARAMS", "BookError", "PaperBook", "Position",
    "book_dir", "is_strategy_name", "paper_home",
    "Intent", "IntentError", "Target", "call_signal", "load_signal", "validate_intent", "wants_holdings",
]
