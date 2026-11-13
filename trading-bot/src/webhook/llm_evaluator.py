"""
LLM-based signal evaluation layer

Architecture derived from sources:
- Cointelegraph article: "ChatGPT-powered bots use NLP and ML to factor in sentiment, news"
- haigane-ai/n8n-ai-trading-signals: "GPT-4 evaluates signal quality, context, and confluence"
- lubbock83-glitch/cognitive-trading-infrastructure: "model returns decision: enter or not"

The LLM acts as a gatekeeper, not a signal generator. It evaluates:
1. Signal quality and confluence
2. Market context
3. Risk/reward assessment
4. News/sentiment if available

Provider configurable via environment variables (supports OpenAI, Anthropic).
"""
import os
import json
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import httpx
from loguru import logger


class SignalAction(Enum):
    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"  # Wait for more confirmation


@dataclass
class SignalDecision:
    """LLM's decision on a trading signal"""
    action: SignalAction
    confidence: float  # 0-1
    reasoning: str
    adjusted_stop: Optional[float] = None
    adjusted_target: Optional[float] = None
    position_size_suggestion: Optional[int] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["action"] = self.action.value
        return d


@dataclass
class MarketContext:
    """Context provided to LLM for decision making"""
    symbol: str
    timeframe: str
    current_price: float
    signal_direction: str  # "buy" or "sell"
    entry_price: float
    stop_loss: float
    take_profit: float
    atr: float
    bias: int  # -1, 0, 1
    
    # Optional enrichment
    recent_highs: List[float] = None
    recent_lows: List[float] = None
    volume_ratio: Optional[float] = None
    news_headlines: List[str] = None
    
    def to_prompt_context(self) -> str:
        """Format context for LLM prompt"""
        lines = [
            f"Symbol: {self.symbol}",
            f"Timeframe: {self.timeframe}",
            f"Current Price: {self.current_price:.2f}",
            f"Signal: {self.signal_direction.upper()}",
            f"Entry Price: {self.entry_price:.2f}",
            f"Stop Loss: {self.stop_loss:.2f}",
            f"Take Profit: {self.take_profit:.2f}",
            f"ATR: {self.atr:.2f}",
            f"Bias: {'BULLISH' if self.bias > 0 else 'BEARISH' if self.bias < 0 else 'NEUTRAL'}",
        ]
        
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        if risk > 0:
            lines.append(f"Risk:Reward: 1:{reward/risk:.2f}")
            lines.append(f"Risk in Points: {risk:.2f}")
        
        if self.recent_highs:
            lines.append(f"Recent Highs: {', '.join(f'{h:.2f}' for h in self.recent_highs[-3:])}")
        if self.recent_lows:
            lines.append(f"Recent Lows: {', '.join(f'{l:.2f}' for l in self.recent_lows[-3:])}")
        if self.volume_ratio:
            lines.append(f"Volume Ratio: {self.volume_ratio:.2f}x average")
        if self.news_headlines:
            lines.append(f"Recent News: {'; '.join(self.news_headlines[:3])}")
            
        return "\n".join(lines)


class LLMEvaluator:
    """
    Evaluates trading signals using an LLM
    
    Supports multiple providers via environment variables:
    - OPENAI_API_KEY: Use OpenAI (default)
    - ANTHROPIC_API_KEY: Use Anthropic Claude
    - LLM_PROVIDER: "openai" or "anthropic" (default: openai)
    - LLM_MODEL: Model name (default: gpt-4o-mini for OpenAI, claude-3-haiku for Anthropic)
    """
    
    SYSTEM_PROMPT = """You are a trading signal evaluator for the TTrades Fractal Model strategy on MNQ futures.

Your role is to act as a risk gate, NOT to generate signals. The Pine Script strategy has already generated a signal based on:
- Multi-timeframe bias alignment
- Swing point identification (C2 closure)
- Change in State of Delivery (CISD) confirmation
- Continuation entry (C3)

Your job is to evaluate whether this signal should be APPROVED, REJECTED, or DEFERRED based on:

1. RISK ASSESSMENT
   - Is the stop loss placement reasonable (beyond protected swing)?
   - Is the risk:reward ratio acceptable (minimum 1:1.5 preferred)?
   - Is the position size appropriate for the account?

2. CONFLUENCE CHECK
   - Does the bias direction align with the trade?
   - Is there sufficient confirmation (CISD present)?
   - Are there conflicting signals?

3. MARKET CONTEXT
   - Any obvious reasons to avoid this trade?
   - Unusual volatility or gap risk?
   - Major news/events pending?

4. TRADE QUALITY
   - Clean setup or messy structure?
   - Entry timing (early in candle vs late)?

IMPORTANT RULES:
- Default to APPROVE unless there's a clear reason to reject
- Be conservative - a missed trade is better than a bad trade
- If in doubt, DEFER (wait for more confirmation)
- Never suggest entering a different trade
- Focus only on the signal presented

Respond in JSON format:
{
    "action": "approve" | "reject" | "defer",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation",
    "warnings": ["Any concerns even if approved"],
    "adjusted_stop": null or new_value,
    "adjusted_target": null or new_value,
    "position_size_suggestion": null or 1-3
}"""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        dry_run: bool = True
    ):
        self.provider = provider or os.getenv("LLM_PROVIDER", "openai")
        self.dry_run = dry_run
        
        if self.provider == "openai":
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
            self.api_url = "https://api.openai.com/v1/chat/completions"
        elif self.provider == "anthropic":
            self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
            self.model = model or os.getenv("LLM_MODEL", "claude-3-haiku-20240307")
            self.api_url = "https://api.anthropic.com/v1/messages"
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")
            
        if not self.api_key and not self.dry_run:
            logger.warning(f"No API key for {self.provider}, falling back to dry run mode")
            self.dry_run = True
            
    async def evaluate_signal(
        self, 
        context: MarketContext,
        timeout: float = 10.0
    ) -> SignalDecision:
        """
        Evaluate a trading signal using the LLM
        
        Args:
            context: Market context for the signal
            timeout: API timeout in seconds
            
        Returns:
            SignalDecision with action, reasoning, and adjustments
        """
        if self.dry_run:
            return self._dry_run_evaluation(context)
            
        try:
            prompt = f"""Evaluate this trading signal:

{context.to_prompt_context()}

Provide your evaluation in the specified JSON format."""

            if self.provider == "openai":
                response = await self._call_openai(prompt, timeout)
            else:
                response = await self._call_anthropic(prompt, timeout)
                
            return self._parse_response(response)
            
        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}")
            # On error, default to defer
            return SignalDecision(
                action=SignalAction.DEFER,
                confidence=0.0,
                reasoning=f"LLM evaluation failed: {str(e)}",
                warnings=["Automatic defer due to evaluation error"]
            )
    
    async def _call_openai(self, prompt: str, timeout: float) -> str:
        """Call OpenAI API"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"}
                },
                timeout=timeout
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    
    async def _call_anthropic(self, prompt: str, timeout: float) -> str:
        """Call Anthropic API"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "system": self.SYSTEM_PROMPT,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.3
                },
                timeout=timeout
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]
    
    def _parse_response(self, response: str) -> SignalDecision:
        """Parse LLM response into SignalDecision"""
        try:
            # Extract JSON from response
            data = json.loads(response)
            
            action_str = data.get("action", "defer").lower()
            action = {
                "approve": SignalAction.APPROVE,
                "reject": SignalAction.REJECT,
                "defer": SignalAction.DEFER
            }.get(action_str, SignalAction.DEFER)
            
            return SignalDecision(
                action=action,
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", "No reasoning provided"),
                adjusted_stop=data.get("adjusted_stop"),
                adjusted_target=data.get("adjusted_target"),
                position_size_suggestion=data.get("position_size_suggestion"),
                warnings=data.get("warnings", [])
            )
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return SignalDecision(
                action=SignalAction.DEFER,
                confidence=0.0,
                reasoning=f"Failed to parse response: {response[:200]}",
                warnings=["Parse error - deferring"]
            )
    
    def _dry_run_evaluation(self, context: MarketContext) -> SignalDecision:
        """
        Dry run evaluation without LLM call
        
        Uses basic rule-based checks as a fallback
        """
        warnings = []
        
        # Check risk:reward
        risk = abs(context.entry_price - context.stop_loss)
        reward = abs(context.take_profit - context.entry_price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        if rr_ratio < 1.5:
            warnings.append(f"Low R:R ratio ({rr_ratio:.2f})")
            
        # Check bias alignment
        if context.signal_direction == "buy" and context.bias < 0:
            warnings.append("Signal against bias (buying in bearish bias)")
        elif context.signal_direction == "sell" and context.bias > 0:
            warnings.append("Signal against bias (selling in bullish bias)")
            
        # Check stop distance
        stop_atr = risk / context.atr if context.atr > 0 else 0
        if stop_atr > 3:
            warnings.append(f"Wide stop ({stop_atr:.1f}x ATR)")
        elif stop_atr < 0.5:
            warnings.append(f"Tight stop ({stop_atr:.1f}x ATR)")
            
        # Decision logic
        if len(warnings) >= 3:
            action = SignalAction.REJECT
            confidence = 0.3
        elif len(warnings) >= 2:
            action = SignalAction.DEFER
            confidence = 0.5
        else:
            action = SignalAction.APPROVE
            confidence = 0.7 if len(warnings) == 0 else 0.6
            
        return SignalDecision(
            action=action,
            confidence=confidence,
            reasoning=f"Dry-run evaluation: {len(warnings)} warnings",
            warnings=warnings
        )
