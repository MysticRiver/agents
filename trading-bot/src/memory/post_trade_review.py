"""
Post-Trade LLM Review - Generates lessons after losing trades.

Design: Uses LLM to analyze losses and generate learnings.
Fallback: Rule-based lesson generation when no API keys available.

Note: This is our own design, not from course text (course uses 
a prompt file for manual LLM review).
"""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import json


@dataclass
class TradeDetails:
    """Details of a closed trade for review."""
    strategy: str
    direction: str  # LONG or SHORT
    entry_price: float
    exit_price: float
    pnl: float
    entry_time: str
    exit_time: str
    setup_id: str
    signal_details: Optional[Dict[str, Any]] = None


class PostTradeReviewer:
    """
    Generates lessons after losing trades.
    
    Works in two modes:
    1. LLM mode: Uses OpenAI/Anthropic to analyze and generate lessons
    2. Dry-run mode: Uses deterministic rule-based fallback
    
    Risk manager remains final authority - this only generates lessons.
    """
    
    def __init__(
        self,
        use_llm: bool = False,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        provider: str = "openai"
    ):
        """
        Initialize post-trade reviewer.
        
        Args:
            use_llm: Whether to use LLM (requires API key)
            api_key: OpenAI or Anthropic API key
            model: Model name
            provider: "openai" or "anthropic"
        """
        self.use_llm = use_llm and api_key is not None
        self.api_key = api_key
        self.model = model
        self.provider = provider
        
        self._client = None
        if self.use_llm:
            self._init_client()
    
    def _init_client(self):
        """Initialize LLM client."""
        try:
            if self.provider == "openai":
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            elif self.provider == "anthropic":
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
        except ImportError:
            self.use_llm = False
            self._client = None
    
    def generate_lesson(self, trade: TradeDetails) -> str:
        """
        Generate a lesson for a losing trade.
        
        Args:
            trade: Details of the losing trade
        
        Returns:
            Plain-English lesson string
        """
        if self.use_llm and self._client:
            return self._generate_llm_lesson(trade)
        else:
            return self._generate_fallback_lesson(trade)
    
    def _generate_llm_lesson(self, trade: TradeDetails) -> str:
        """Generate lesson using LLM."""
        prompt = self._build_prompt(trade)
        
        try:
            if self.provider == "openai":
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a trading coach analyzing a losing trade. "
                                "Write ONE concise lesson (1-2 sentences) that the bot "
                                "should remember before taking a similar trade. Focus on "
                                "what could be improved or avoided. Be specific to the "
                                "strategy and conditions."
                            )
                        },
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=150,
                    temperature=0.3
                )
                return response.choices[0].message.content.strip()
            
            elif self.provider == "anthropic":
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=150,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    system=(
                        "You are a trading coach analyzing a losing trade. "
                        "Write ONE concise lesson (1-2 sentences) that the bot "
                        "should remember before taking a similar trade."
                    )
                )
                return response.content[0].text.strip()
        
        except Exception as e:
            # Fallback on any LLM error
            return self._generate_fallback_lesson(trade)
    
    def _generate_fallback_lesson(self, trade: TradeDetails) -> str:
        """
        Generate lesson using deterministic rules.
        
        This is our own design for dry-run mode without API keys.
        """
        lessons = []
        
        # Calculate loss percentage
        if trade.direction == "LONG":
            loss_pct = ((trade.exit_price - trade.entry_price) / trade.entry_price) * 100
        else:
            loss_pct = ((trade.entry_price - trade.exit_price) / trade.entry_price) * 100
        
        # Rule 1: Large loss
        if abs(loss_pct) > 2.0:
            lessons.append(
                f"AVOID {trade.strategy} {trade.direction.lower()} entries with >2% adverse move risk"
            )
        
        # Rule 2: Strategy-specific lessons
        strategy_lower = trade.strategy.lower()
        
        if "fractal" in strategy_lower:
            if trade.direction == "LONG":
                lessons.append(
                    f"WAIT for stronger HTF trend confirmation before {trade.strategy} long entries"
                )
            else:
                lessons.append(
                    f"VERIFY swing low break before {trade.strategy} short entries"
                )
        
        elif "crossover" in strategy_lower or "ma_" in strategy_lower:
            if trade.direction == "LONG":
                lessons.append(
                    f"CHECK for false crossover in choppy conditions before {trade.strategy} longs"
                )
            else:
                lessons.append(
                    f"CONFIRM trend direction before {trade.strategy} shorts"
                )
        
        elif "breakout" in strategy_lower:
            lessons.append(
                f"VERIFY volume confirmation on {trade.strategy} entries"
            )
        
        elif "rsi" in strategy_lower or "overbought" in strategy_lower or "oversold" in strategy_lower:
            lessons.append(
                f"WAIT for divergence confirmation on {trade.strategy} signals"
            )
        
        else:
            # Generic lesson
            lessons.append(
                f"REVIEW {trade.strategy} {trade.direction.lower()} setup conditions before repeating"
            )
        
        # Rule 3: Time-based observations
        try:
            entry_dt = datetime.fromisoformat(trade.entry_time)
            hour = entry_dt.hour
            
            if hour < 10:  # Early session
                lessons.append("CAUTION with early session entries before 10:00")
            elif hour >= 15:  # Late session
                lessons.append("AVOID late session entries after 15:00")
        except (ValueError, AttributeError):
            pass
        
        # Combine lessons
        if lessons:
            return " | ".join(lessons[:2])  # Max 2 lessons
        else:
            return f"REVIEW {trade.strategy} {trade.direction.lower()} entry conditions"
    
    def _build_prompt(self, trade: TradeDetails) -> str:
        """Build prompt for LLM analysis."""
        signal_info = ""
        if trade.signal_details:
            signal_info = f"\nSignal details: {json.dumps(trade.signal_details, indent=2)}"
        
        return f"""
Analyze this losing trade and write ONE concise lesson:

Strategy: {trade.strategy}
Direction: {trade.direction}
Entry: ${trade.entry_price:.2f} at {trade.entry_time}
Exit: ${trade.exit_price:.2f} at {trade.exit_time}
PnL: ${trade.pnl:.2f}
Setup ID: {trade.setup_id}
{signal_info}

Write a specific, actionable lesson for the bot to remember.
Format: "AVOID/WAIT/CHECK/VERIFY [specific condition] before [action]"
"""
    
    def review_and_learn(
        self,
        trade: TradeDetails,
        learnings_file: "LearningsFile"
    ) -> str:
        """
        Complete post-trade review: generate lesson and write to learnings file.
        
        Args:
            trade: Details of the losing trade
            learnings_file: LearningsFile instance to write to
        
        Returns:
            The generated lesson
        """
        # Only review losses
        if trade.pnl >= 0:
            return ""
        
        lesson = self.generate_lesson(trade)
        
        learnings_file.write_lesson(
            strategy=trade.strategy,
            direction=trade.direction,
            setup_id=trade.setup_id,
            lesson=lesson
        )
        
        return lesson
