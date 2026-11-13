"""
Trade Ledger - Records all trading decisions and outcomes.

Based on Skool course design:
- CSV format for simplicity and auditability
- Fields: timestamp, action, setup_id, outcome, pnl, outcome_lesson, avoided_by_memory

Course text: "Records when a decision happened, what action was taken or skipped,
why the rule fired, and how a closed trade ended."
"""

import csv
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import json


@dataclass
class LedgerEntry:
    """Single entry in the trade ledger."""
    timestamp: str
    action: str  # BUY, SELL, SKIP
    setup_id: str  # Identifier for the setup (e.g., "fractal_long_25000")
    strategy: str  # Strategy name
    direction: str  # LONG, SHORT
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    outcome: Optional[str] = None  # WIN, LOSS, PENDING
    pnl: Optional[float] = None
    outcome_lesson: Optional[str] = None  # Plain-text lesson if loss
    avoided_by_memory: bool = False  # True if skipped due to prior lesson
    skip_reason: Optional[str] = None  # Why was it skipped
    signal_details: Optional[str] = None  # JSON string of signal details


class TradeLedger:
    """
    Trade ledger following course design.
    
    Records all trading decisions in CSV format:
    - Every signal is logged (BUY, SELL, or SKIP)
    - Outcomes updated when trades close
    - Lessons written after losses
    """
    
    FIELDNAMES = [
        "timestamp", "action", "setup_id", "strategy", "direction",
        "entry_price", "exit_price", "outcome", "pnl",
        "outcome_lesson", "avoided_by_memory", "skip_reason", "signal_details"
    ]
    
    def __init__(self, ledger_path: str = "trade_ledger.csv"):
        """
        Initialize trade ledger.
        
        Args:
            ledger_path: Path to CSV ledger file
        """
        self.ledger_path = Path(ledger_path)
        self._ensure_ledger_exists()
    
    def _ensure_ledger_exists(self):
        """Create ledger file with headers if it doesn't exist."""
        if not self.ledger_path.exists():
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writeheader()
    
    def log_signal(
        self,
        action: str,
        setup_id: str,
        strategy: str,
        direction: str,
        entry_price: Optional[float] = None,
        avoided_by_memory: bool = False,
        skip_reason: Optional[str] = None,
        signal_details: Optional[dict] = None
    ) -> LedgerEntry:
        """
        Log a trading signal/decision.
        
        Args:
            action: BUY, SELL, or SKIP
            setup_id: Unique identifier for this setup
            strategy: Strategy name
            direction: LONG or SHORT
            entry_price: Entry price if executed
            avoided_by_memory: True if skipped due to memory gate
            skip_reason: Why signal was skipped
            signal_details: Additional signal information
        
        Returns:
            The logged entry
        """
        entry = LedgerEntry(
            timestamp=datetime.now().isoformat(),
            action=action,
            setup_id=setup_id,
            strategy=strategy,
            direction=direction,
            entry_price=entry_price,
            avoided_by_memory=avoided_by_memory,
            skip_reason=skip_reason,
            signal_details=json.dumps(signal_details) if signal_details else None
        )
        
        self._write_entry(entry)
        return entry
    
    def update_outcome(
        self,
        setup_id: str,
        exit_price: float,
        outcome: str,
        pnl: float,
        outcome_lesson: Optional[str] = None
    ):
        """
        Update a trade's outcome after it closes.
        
        Args:
            setup_id: The setup identifier to update
            exit_price: Exit price
            outcome: WIN or LOSS
            pnl: Profit/loss amount
            outcome_lesson: Lesson if loss (written by PostTradeReviewer)
        """
        entries = self._read_all()
        updated = False
        
        for entry in entries:
            if entry["setup_id"] == setup_id and entry["outcome"] in (None, "", "PENDING"):
                entry["exit_price"] = exit_price
                entry["outcome"] = outcome
                entry["pnl"] = pnl
                entry["outcome_lesson"] = outcome_lesson
                updated = True
                break
        
        if updated:
            self._write_all(entries)
    
    def get_recent_losses(
        self,
        strategy: Optional[str] = None,
        direction: Optional[str] = None,
        window_hours: float = 24.0
    ) -> List[dict]:
        """
        Get recent losing trades for memory gate.
        
        Args:
            strategy: Filter by strategy name
            direction: Filter by direction (LONG/SHORT)
            window_hours: How far back to look
        
        Returns:
            List of recent losing trade entries
        """
        entries = self._read_all()
        cutoff = datetime.now().timestamp() - (window_hours * 3600)
        
        losses = []
        for entry in entries:
            if entry["outcome"] != "LOSS":
                continue
            
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"]).timestamp()
            except (ValueError, TypeError):
                continue
            
            if entry_time < cutoff:
                continue
            
            if strategy and entry.get("strategy") != strategy:
                continue
            
            if direction and entry.get("direction") != direction:
                continue
            
            losses.append(entry)
        
        return losses
    
    def get_all_entries(self) -> List[dict]:
        """Get all ledger entries."""
        return self._read_all()
    
    def clear(self):
        """Clear all entries (for testing)."""
        with open(self.ledger_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writeheader()
    
    def _write_entry(self, entry: LedgerEntry):
        """Append a single entry to the ledger."""
        with open(self.ledger_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writerow(asdict(entry))
    
    def _read_all(self) -> List[dict]:
        """Read all entries from the ledger."""
        if not self.ledger_path.exists():
            return []
        
        with open(self.ledger_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)
    
    def _write_all(self, entries: List[dict]):
        """Rewrite all entries to the ledger."""
        with open(self.ledger_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            writer.writerows(entries)
