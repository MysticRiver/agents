"""
Learnings File and Memory Gate.

Based on Skool course design:
- learnings.txt: Plain-English lessons written after losses
- Memory gate: Skips signals matching recent failed patterns

Course text: "Write one concise lesson after a loss. Read relevant lessons 
before repeating a setup. This simple gate is intentionally conservative."
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple


@dataclass
class Learning:
    """A single lesson from a losing trade."""
    timestamp: str
    strategy: str
    direction: str
    setup_id: str
    lesson: str
    
    def to_line(self) -> str:
        """Convert to line format for learnings.txt"""
        return f"[{self.timestamp}] {self.strategy}/{self.direction}: {self.lesson}"
    
    @classmethod
    def from_line(cls, line: str) -> Optional["Learning"]:
        """Parse a line from learnings.txt"""
        match = re.match(
            r"\[([^\]]+)\]\s+([^/]+)/([^:]+):\s+(.+)",
            line.strip()
        )
        if match:
            return cls(
                timestamp=match.group(1),
                strategy=match.group(2),
                direction=match.group(3),
                setup_id="",  # Not stored in line format
                lesson=match.group(4)
            )
        return None


class LearningsFile:
    """
    Learnings file following course design.
    
    Course text: "Two-file memory system:
    - Ledger: Records what happened (factual trade history)
    - Learnings: Stores plain English lesson after trade closes"
    """
    
    def __init__(self, learnings_path: str = "learnings.txt"):
        """
        Initialize learnings file.
        
        Args:
            learnings_path: Path to learnings text file
        """
        self.learnings_path = Path(learnings_path)
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Create learnings file if it doesn't exist."""
        if not self.learnings_path.exists():
            self.learnings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.learnings_path, "w") as f:
                f.write("# Trading Bot Learnings\n")
                f.write("# Format: [timestamp] strategy/direction: lesson\n")
                f.write("# Bot reads these before repeating a setup\n\n")
    
    def write_lesson(
        self,
        strategy: str,
        direction: str,
        setup_id: str,
        lesson: str
    ) -> Learning:
        """
        Write a lesson after a losing trade.
        
        Course text: "Write one concise lesson after a loss."
        
        Args:
            strategy: Strategy name
            direction: LONG or SHORT
            setup_id: Setup identifier
            lesson: Plain-English lesson
        
        Returns:
            The written learning
        """
        learning = Learning(
            timestamp=datetime.now().isoformat(),
            strategy=strategy,
            direction=direction,
            setup_id=setup_id,
            lesson=lesson
        )
        
        with open(self.learnings_path, "a") as f:
            f.write(learning.to_line() + "\n")
        
        return learning
    
    def read_lessons(
        self,
        strategy: Optional[str] = None,
        direction: Optional[str] = None,
        window_hours: Optional[float] = None
    ) -> List[Learning]:
        """
        Read relevant lessons for pre-trade evaluation.
        
        Course text: "Read relevant lessons before repeating a setup."
        
        Args:
            strategy: Filter by strategy
            direction: Filter by direction
            window_hours: Only lessons within this time window
        
        Returns:
            List of relevant learnings
        """
        if not self.learnings_path.exists():
            return []
        
        lessons = []
        cutoff = None
        if window_hours:
            cutoff = datetime.now() - timedelta(hours=window_hours)
        
        with open(self.learnings_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                learning = Learning.from_line(line)
                if not learning:
                    continue
                
                # Filter by strategy
                if strategy and learning.strategy != strategy:
                    continue
                
                # Filter by direction
                if direction and learning.direction != direction:
                    continue
                
                # Filter by time window
                if cutoff:
                    try:
                        lesson_time = datetime.fromisoformat(learning.timestamp)
                        if lesson_time < cutoff:
                            continue
                    except ValueError:
                        continue
                
                lessons.append(learning)
        
        return lessons
    
    def has_recent_lesson(
        self,
        strategy: str,
        direction: str,
        window_hours: float = 24.0
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if there's a recent lesson for this setup.
        
        Args:
            strategy: Strategy name
            direction: LONG or SHORT
            window_hours: How far back to look
        
        Returns:
            (has_lesson, lesson_text)
        """
        lessons = self.read_lessons(
            strategy=strategy,
            direction=direction,
            window_hours=window_hours
        )
        
        if lessons:
            return True, lessons[-1].lesson
        return False, None
    
    def clear(self):
        """Clear all lessons (for testing)."""
        with open(self.learnings_path, "w") as f:
            f.write("# Trading Bot Learnings\n")
            f.write("# Format: [timestamp] strategy/direction: lesson\n")
            f.write("# Bot reads these before repeating a setup\n\n")


class MemoryGate:
    """
    Memory gate that skips signals matching recent failed patterns.
    
    Course text: "This simple gate is intentionally conservative. A more 
    advanced system would evaluate richer context instead of treating 
    every crossover as identical."
    
    Design decision (our own, not from course): Window and on/off configurable.
    """
    
    def __init__(
        self,
        learnings_file: LearningsFile,
        enabled: bool = True,
        window_hours: float = 24.0
    ):
        """
        Initialize memory gate.
        
        Args:
            learnings_file: LearningsFile instance to read from
            enabled: Whether the gate is active
            window_hours: How far back to look for losses
        """
        self.learnings = learnings_file
        self.enabled = enabled
        self.window_hours = window_hours
    
    def should_skip(
        self,
        strategy: str,
        direction: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if this signal should be skipped due to recent loss.
        
        Course test case: "Repeated losing setup with memory on: Expect SKIP"
        
        Args:
            strategy: Strategy name
            direction: LONG or SHORT
        
        Returns:
            (should_skip, reason)
        """
        if not self.enabled:
            return False, None
        
        has_lesson, lesson = self.learnings.has_recent_lesson(
            strategy=strategy,
            direction=direction,
            window_hours=self.window_hours
        )
        
        if has_lesson:
            reason = f"Memory gate: Recent loss on {strategy}/{direction}. Lesson: {lesson}"
            return True, reason
        
        return False, None
    
    def evaluate(
        self,
        strategy: str,
        direction: str
    ) -> dict:
        """
        Evaluate signal against memory gate.
        
        Returns:
            Dict with evaluation result
        """
        should_skip, reason = self.should_skip(strategy, direction)
        
        return {
            "gate_enabled": self.enabled,
            "window_hours": self.window_hours,
            "should_skip": should_skip,
            "reason": reason,
            "recent_lessons": [
                l.lesson for l in self.learnings.read_lessons(
                    strategy=strategy,
                    direction=direction,
                    window_hours=self.window_hours
                )
            ]
        }
