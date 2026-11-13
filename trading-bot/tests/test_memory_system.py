"""
Unit tests for the memory/learning system.

Includes the course's key test case:
- Same signal after a loss is SKIPPED with memory ON
- Same signal after a loss is EXECUTED with memory OFF
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path

from src.memory import TradeLedger, LearningsFile, MemoryGate, PostTradeReviewer
from src.memory.post_trade_review import TradeDetails


class TestTradeLedger:
    """Tests for trade ledger functionality."""
    
    @pytest.fixture
    def ledger(self, tmp_path):
        """Create ledger with temp file."""
        path = tmp_path / "trade_ledger.csv"
        return TradeLedger(str(path))
    
    def test_create_ledger(self, ledger):
        """Ledger file is created with headers."""
        assert ledger.ledger_path.exists()
    
    def test_log_signal_buy(self, ledger):
        """Log a BUY signal."""
        entry = ledger.log_signal(
            action="BUY",
            setup_id="fractal_long_001",
            strategy="fractal_model",
            direction="LONG",
            entry_price=25000.0
        )
        assert entry.action == "BUY"
        assert entry.strategy == "fractal_model"
        
        entries = ledger.get_all_entries()
        assert len(entries) == 1
        assert entries[0]["action"] == "BUY"
    
    def test_log_signal_skip(self, ledger):
        """Log a SKIP signal with reason."""
        entry = ledger.log_signal(
            action="SKIP",
            setup_id="fractal_long_002",
            strategy="fractal_model",
            direction="LONG",
            avoided_by_memory=True,
            skip_reason="Recent loss on similar setup"
        )
        assert entry.action == "SKIP"
        assert entry.avoided_by_memory == True
        
        entries = ledger.get_all_entries()
        assert entries[0]["avoided_by_memory"] == "True"
    
    def test_update_outcome_loss(self, ledger):
        """Update trade outcome to LOSS with lesson."""
        ledger.log_signal(
            action="BUY",
            setup_id="fractal_long_003",
            strategy="fractal_model",
            direction="LONG",
            entry_price=25000.0
        )
        
        ledger.update_outcome(
            setup_id="fractal_long_003",
            exit_price=24900.0,
            outcome="LOSS",
            pnl=-200.0,
            outcome_lesson="AVOID long entries without HTF confirmation"
        )
        
        entries = ledger.get_all_entries()
        assert entries[0]["outcome"] == "LOSS"
        assert entries[0]["pnl"] == "-200.0"
        assert "AVOID" in entries[0]["outcome_lesson"]
    
    def test_get_recent_losses(self, ledger):
        """Get recent losing trades."""
        # Create a loss
        ledger.log_signal(
            action="BUY",
            setup_id="test_001",
            strategy="fractal_model",
            direction="LONG",
            entry_price=25000.0
        )
        ledger.update_outcome(
            setup_id="test_001",
            exit_price=24900.0,
            outcome="LOSS",
            pnl=-200.0
        )
        
        # Create a win
        ledger.log_signal(
            action="SELL",
            setup_id="test_002",
            strategy="fractal_model",
            direction="SHORT",
            entry_price=25000.0
        )
        ledger.update_outcome(
            setup_id="test_002",
            exit_price=24800.0,
            outcome="WIN",
            pnl=400.0
        )
        
        losses = ledger.get_recent_losses(strategy="fractal_model")
        assert len(losses) == 1
        assert losses[0]["outcome"] == "LOSS"


class TestLearningsFile:
    """Tests for learnings file functionality."""
    
    @pytest.fixture
    def learnings(self, tmp_path):
        """Create learnings file with temp path."""
        path = tmp_path / "learnings.txt"
        return LearningsFile(str(path))
    
    def test_create_learnings_file(self, learnings):
        """Learnings file is created with header."""
        assert learnings.learnings_path.exists()
        content = learnings.learnings_path.read_text()
        assert "Trading Bot Learnings" in content
    
    def test_write_lesson(self, learnings):
        """Write a lesson after loss."""
        learning = learnings.write_lesson(
            strategy="fractal_model",
            direction="LONG",
            setup_id="fractal_long_001",
            lesson="AVOID long entries without HTF trend confirmation"
        )
        
        assert learning.strategy == "fractal_model"
        assert "AVOID" in learning.lesson
        
        # Verify written to file
        content = learnings.learnings_path.read_text()
        assert "fractal_model/LONG" in content
        assert "AVOID" in content
    
    def test_read_lessons_filtered(self, learnings):
        """Read lessons filtered by strategy and direction."""
        learnings.write_lesson(
            strategy="fractal_model",
            direction="LONG",
            setup_id="001",
            lesson="Lesson for fractal long"
        )
        learnings.write_lesson(
            strategy="ma_crossover",
            direction="SHORT",
            setup_id="002",
            lesson="Lesson for MA short"
        )
        
        fractal_lessons = learnings.read_lessons(strategy="fractal_model")
        assert len(fractal_lessons) == 1
        assert "fractal long" in fractal_lessons[0].lesson
        
        short_lessons = learnings.read_lessons(direction="SHORT")
        assert len(short_lessons) == 1
        assert "MA short" in short_lessons[0].lesson
    
    def test_has_recent_lesson(self, learnings):
        """Check for recent lesson."""
        learnings.write_lesson(
            strategy="fractal_model",
            direction="LONG",
            setup_id="001",
            lesson="Recent lesson"
        )
        
        has_lesson, text = learnings.has_recent_lesson(
            strategy="fractal_model",
            direction="LONG",
            window_hours=24.0
        )
        assert has_lesson == True
        assert "Recent lesson" in text
        
        # No lesson for different direction
        has_lesson, text = learnings.has_recent_lesson(
            strategy="fractal_model",
            direction="SHORT",
            window_hours=24.0
        )
        assert has_lesson == False


class TestMemoryGate:
    """Tests for memory gate functionality.
    
    Course test case: "Repeated losing setup with memory on: Expect SKIP"
    Course test case: "Repeated avoided setup with memory disabled: Expect BUY if crossover occurs"
    """
    
    @pytest.fixture
    def learnings(self, tmp_path):
        path = tmp_path / "learnings.txt"
        return LearningsFile(str(path))
    
    def test_memory_gate_skip_after_loss(self, learnings):
        """
        COURSE TEST: Same signal after a loss is SKIPPED with memory ON.
        
        Course text: "Repeated losing setup with memory on: Expect SKIP"
        """
        # Write a lesson (simulates loss)
        learnings.write_lesson(
            strategy="fractal_model",
            direction="LONG",
            setup_id="001",
            lesson="Lost on this setup"
        )
        
        # Create memory gate with memory ON
        gate = MemoryGate(learnings, enabled=True, window_hours=24.0)
        
        # Same signal should be SKIPPED
        should_skip, reason = gate.should_skip(
            strategy="fractal_model",
            direction="LONG"
        )
        
        assert should_skip == True, "Memory ON should skip after loss"
        assert "Memory gate" in reason
        assert "Lost on this setup" in reason
    
    def test_memory_gate_execute_without_loss(self, learnings):
        """Signal executes when no recent loss exists."""
        gate = MemoryGate(learnings, enabled=True, window_hours=24.0)
        
        # No prior loss
        should_skip, reason = gate.should_skip(
            strategy="fractal_model",
            direction="LONG"
        )
        
        assert should_skip == False, "Should execute with no prior loss"
        assert reason is None
    
    def test_memory_gate_disabled_executes(self, learnings):
        """
        COURSE TEST: Same signal after a loss is EXECUTED with memory OFF.
        
        Course text: "Repeated avoided setup with memory disabled: Expect BUY if crossover occurs"
        """
        # Write a lesson (simulates loss)
        learnings.write_lesson(
            strategy="fractal_model",
            direction="LONG",
            setup_id="001",
            lesson="Lost on this setup"
        )
        
        # Create memory gate with memory OFF
        gate = MemoryGate(learnings, enabled=False, window_hours=24.0)
        
        # Same signal should be EXECUTED (not skipped)
        should_skip, reason = gate.should_skip(
            strategy="fractal_model",
            direction="LONG"
        )
        
        assert should_skip == False, "Memory OFF should execute even after loss"
        assert reason is None
    
    def test_memory_gate_different_direction_executes(self, learnings):
        """Different direction should not be blocked."""
        learnings.write_lesson(
            strategy="fractal_model",
            direction="LONG",
            setup_id="001",
            lesson="Lost on long"
        )
        
        gate = MemoryGate(learnings, enabled=True, window_hours=24.0)
        
        # SHORT should not be blocked by LONG loss
        should_skip, reason = gate.should_skip(
            strategy="fractal_model",
            direction="SHORT"
        )
        
        assert should_skip == False, "Short should not be blocked by long loss"
    
    def test_memory_gate_window_expires(self, learnings):
        """Lessons outside window should not block."""
        # Manually write an old lesson
        old_time = (datetime.now() - timedelta(hours=48)).isoformat()
        with open(learnings.learnings_path, "a") as f:
            f.write(f"[{old_time}] fractal_model/LONG: Old lesson\n")
        
        gate = MemoryGate(learnings, enabled=True, window_hours=24.0)
        
        # Should not be blocked (lesson is too old)
        should_skip, reason = gate.should_skip(
            strategy="fractal_model",
            direction="LONG"
        )
        
        assert should_skip == False, "Old lessons should not block"


class TestPostTradeReviewer:
    """Tests for post-trade lesson generation."""
    
    @pytest.fixture
    def reviewer(self):
        """Create reviewer in dry-run mode."""
        return PostTradeReviewer(use_llm=False)
    
    @pytest.fixture
    def learnings(self, tmp_path):
        path = tmp_path / "learnings.txt"
        return LearningsFile(str(path))
    
    def test_generate_lesson_fractal_long(self, reviewer):
        """Generate lesson for fractal long loss."""
        trade = TradeDetails(
            strategy="fractal_model",
            direction="LONG",
            entry_price=25000.0,
            exit_price=24900.0,
            pnl=-200.0,
            entry_time="2026-01-01T10:00:00",
            exit_time="2026-01-01T12:00:00",
            setup_id="fractal_long_001"
        )
        
        lesson = reviewer.generate_lesson(trade)
        
        assert len(lesson) > 0
        assert any(word in lesson.upper() for word in ["WAIT", "AVOID", "CHECK", "VERIFY", "REVIEW"])
    
    def test_generate_lesson_ma_crossover(self, reviewer):
        """Generate lesson for MA crossover loss."""
        trade = TradeDetails(
            strategy="ma_crossover_trend",
            direction="LONG",
            entry_price=25000.0,
            exit_price=24800.0,
            pnl=-400.0,
            entry_time="2026-01-01T10:00:00",
            exit_time="2026-01-01T14:00:00",
            setup_id="ma_long_001"
        )
        
        lesson = reviewer.generate_lesson(trade)
        
        assert len(lesson) > 0
        assert "crossover" in lesson.lower() or "ma" in lesson.lower()
    
    def test_review_and_learn_writes_lesson(self, reviewer, learnings):
        """Complete review writes lesson to learnings file."""
        trade = TradeDetails(
            strategy="fractal_model",
            direction="LONG",
            entry_price=25000.0,
            exit_price=24900.0,
            pnl=-200.0,
            entry_time="2026-01-01T10:00:00",
            exit_time="2026-01-01T12:00:00",
            setup_id="fractal_long_001"
        )
        
        lesson = reviewer.review_and_learn(trade, learnings)
        
        assert len(lesson) > 0
        
        # Verify written to file
        lessons = learnings.read_lessons(strategy="fractal_model")
        assert len(lessons) == 1
    
    def test_no_lesson_for_win(self, reviewer, learnings):
        """No lesson generated for winning trade."""
        trade = TradeDetails(
            strategy="fractal_model",
            direction="LONG",
            entry_price=25000.0,
            exit_price=25200.0,
            pnl=400.0,  # Positive = win
            entry_time="2026-01-01T10:00:00",
            exit_time="2026-01-01T12:00:00",
            setup_id="fractal_long_002"
        )
        
        lesson = reviewer.review_and_learn(trade, learnings)
        
        assert lesson == ""
        
        # No lesson written
        lessons = learnings.read_lessons(strategy="fractal_model")
        assert len(lessons) == 0


class TestIntegration:
    """Integration tests for the full memory system."""
    
    @pytest.fixture
    def setup(self, tmp_path):
        """Setup all components."""
        ledger = TradeLedger(str(tmp_path / "ledger.csv"))
        learnings = LearningsFile(str(tmp_path / "learnings.txt"))
        gate = MemoryGate(learnings, enabled=True, window_hours=24.0)
        reviewer = PostTradeReviewer(use_llm=False)
        return ledger, learnings, gate, reviewer
    
    def test_full_cycle_loss_then_skip(self, setup):
        """
        Full cycle: execute trade, lose, generate lesson, skip next signal.
        
        This tests the course's core learning loop.
        """
        ledger, learnings, gate, reviewer = setup
        
        # Step 1: Log initial signal and entry
        ledger.log_signal(
            action="BUY",
            setup_id="test_001",
            strategy="fractal_model",
            direction="LONG",
            entry_price=25000.0
        )
        
        # Step 2: Trade loses
        trade = TradeDetails(
            strategy="fractal_model",
            direction="LONG",
            entry_price=25000.0,
            exit_price=24900.0,
            pnl=-200.0,
            entry_time="2026-01-01T10:00:00",
            exit_time="2026-01-01T12:00:00",
            setup_id="test_001"
        )
        
        # Step 3: Generate and write lesson
        lesson = reviewer.review_and_learn(trade, learnings)
        assert len(lesson) > 0
        
        # Update ledger with outcome
        ledger.update_outcome(
            setup_id="test_001",
            exit_price=24900.0,
            outcome="LOSS",
            pnl=-200.0,
            outcome_lesson=lesson
        )
        
        # Step 4: Next similar signal should be SKIPPED
        should_skip, reason = gate.should_skip(
            strategy="fractal_model",
            direction="LONG"
        )
        
        assert should_skip == True, "Should skip after documented loss"
        
        # Log the skip
        ledger.log_signal(
            action="SKIP",
            setup_id="test_002",
            strategy="fractal_model",
            direction="LONG",
            avoided_by_memory=True,
            skip_reason=reason
        )
        
        # Verify ledger has both entries
        entries = ledger.get_all_entries()
        assert len(entries) == 2
        assert entries[0]["outcome"] == "LOSS"
        assert entries[1]["action"] == "SKIP"
        assert entries[1]["avoided_by_memory"] == "True"
    
    def test_memory_on_vs_off_comparison(self, tmp_path):
        """
        Compare behavior with memory ON vs OFF.
        
        This directly tests the course's specification:
        - Memory ON: Skip after loss
        - Memory OFF: Execute anyway
        """
        # Setup with shared learnings
        learnings = LearningsFile(str(tmp_path / "learnings.txt"))
        
        # Write a loss lesson
        learnings.write_lesson(
            strategy="fractal_model",
            direction="LONG",
            setup_id="loss_001",
            lesson="Recent loss - should trigger skip"
        )
        
        # Test with memory ON
        gate_on = MemoryGate(learnings, enabled=True, window_hours=24.0)
        skip_on, _ = gate_on.should_skip("fractal_model", "LONG")
        
        # Test with memory OFF
        gate_off = MemoryGate(learnings, enabled=False, window_hours=24.0)
        skip_off, _ = gate_off.should_skip("fractal_model", "LONG")
        
        assert skip_on == True, "Memory ON should skip"
        assert skip_off == False, "Memory OFF should execute"
