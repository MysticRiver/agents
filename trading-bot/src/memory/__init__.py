"""
Memory system for learning from trading mistakes.

Based on the Miles Deutscher / Skool course architecture:
- Trade ledger: Records all decisions and outcomes
- Learnings file: Plain-English lessons after losses
- Memory gate: Skips signals matching recent failed patterns

Note: Course videos were not viewed. Implementation follows course text.
"""

from .trade_ledger import TradeLedger
from .learnings import LearningsFile, MemoryGate
from .post_trade_review import PostTradeReviewer

__all__ = ["TradeLedger", "LearningsFile", "MemoryGate", "PostTradeReviewer"]
