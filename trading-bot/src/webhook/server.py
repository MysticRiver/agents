"""
Webhook server for TradingView alerts with LLM evaluation

Architecture derived from sources:
- Cointelegraph article: TradingView → webhook → AI evaluation → execution
- haigane-ai/n8n-ai-trading-signals: Webhook → Validation → GPT-4 → Risk filter → Execution
- lubbock83-glitch/cognitive-trading-infrastructure: Edge function validates, dedupes, then LLM decides
- Miles Deutscher Skool course (structure visible, content behind membership):
  - Day 5: "Inspectable Memory" suggests trade ledger/logging
  - Day 6: "Stress Test" suggests validation and safety checks
  - Day 7: "Supervised Paper Trial" suggests dry-run mode

Flow:
1. Receive TradingView webhook (JSON payload)
2. Validate schema and shared secret
3. Check freshness (reject stale signals)
4. Deduplicate (prevent double entries)
5. Enrich with market context
6. LLM evaluation (approve/reject/defer)
7. Risk management check
8. Route to NinjaTrader (or log in paper mode)
"""
import os
import json
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from collections import deque

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from loguru import logger

from .llm_evaluator import LLMEvaluator, MarketContext, SignalDecision, SignalAction
from ..risk.manager import RiskManager, RiskConfig
from ..broker.ninjatrader import NinjaTraderConnection, OrderManager, OrderAction


# ============================================================================
# CONFIGURATION
# ============================================================================

class WebhookConfig:
    """Webhook server configuration from environment"""
    
    def __init__(self):
        self.secret = os.getenv("WEBHOOK_SECRET", "")
        self.max_signal_age_ms = int(os.getenv("MAX_SIGNAL_AGE_MS", "30000"))  # 30 seconds
        self.dedupe_window_ms = int(os.getenv("DEDUPE_WINDOW_MS", "60000"))  # 1 minute
        self.paper_mode = os.getenv("PAPER_MODE", "true").lower() == "true"
        self.log_all_signals = os.getenv("LOG_ALL_SIGNALS", "true").lower() == "true"
        
        # NinjaTrader connection
        self.nt_host = os.getenv("NT_HOST", "127.0.0.1")
        self.nt_port = int(os.getenv("NT_PORT", "36973"))
        self.nt_account = os.getenv("NT_ACCOUNT", "Sim101")
        
        # Risk settings
        self.max_position_size = int(os.getenv("MAX_POSITION_SIZE", "3"))
        self.max_daily_loss = float(os.getenv("MAX_DAILY_LOSS", "500"))


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class TradingViewSignal(BaseModel):
    """
    Signal payload from TradingView Pine Script
    
    Expected format from Pine Script alert():
    {
        "action": "buy" | "sell",
        "symbol": "MNQ",
        "price": 18500.25,
        "stop": 18480.00,
        "target": 18540.50,
        "atr": 15.5,
        "bias": 1,
        "timestamp": 1699999999999,
        "secret": "your_shared_secret"
    }
    """
    action: str = Field(..., regex="^(buy|sell)$")
    symbol: str = Field(default="MNQ")
    price: float = Field(..., gt=0)
    stop: float = Field(..., gt=0)
    target: float = Field(..., gt=0)
    atr: float = Field(..., gt=0)
    bias: int = Field(..., ge=-1, le=1)
    timestamp: int = Field(...)
    secret: str = Field(default="")
    
    # Optional enrichment fields
    timeframe: str = Field(default="5m")
    strategy: str = Field(default="fractal_model")
    
    @validator("action")
    def validate_action(cls, v):
        return v.lower()


class WebhookResponse(BaseModel):
    """Response to TradingView webhook"""
    status: str
    message: str
    signal_id: Optional[str] = None
    decision: Optional[Dict] = None
    order_id: Optional[str] = None


# ============================================================================
# SIGNAL PROCESSOR
# ============================================================================

@dataclass
class ProcessedSignal:
    """Internal representation of a processed signal"""
    signal_id: str
    received_at: datetime
    payload: TradingViewSignal
    decision: Optional[SignalDecision] = None
    order_id: Optional[str] = None
    execution_result: Optional[str] = None
    
    def to_log_entry(self) -> Dict:
        """Format for trade ledger logging"""
        return {
            "signal_id": self.signal_id,
            "received_at": self.received_at.isoformat(),
            "action": self.payload.action,
            "symbol": self.payload.symbol,
            "price": self.payload.price,
            "stop": self.payload.stop,
            "target": self.payload.target,
            "decision": self.decision.to_dict() if self.decision else None,
            "order_id": self.order_id,
            "execution_result": self.execution_result
        }


class SignalProcessor:
    """
    Processes TradingView signals through the evaluation pipeline
    
    Pipeline:
    1. Validate → 2. Dedupe → 3. Enrich → 4. LLM Evaluate → 5. Risk Check → 6. Execute
    """
    
    def __init__(self, config: WebhookConfig):
        self.config = config
        self.llm_evaluator = LLMEvaluator(dry_run=config.paper_mode)
        self.risk_manager = RiskManager(RiskConfig(
            max_position_size=config.max_position_size,
            max_daily_loss=config.max_daily_loss
        ))
        
        # NinjaTrader connection (lazy initialized)
        self._nt_connection: Optional[NinjaTraderConnection] = None
        self._order_manager: Optional[OrderManager] = None
        
        # Deduplication cache
        self._recent_signals: deque = deque(maxlen=100)
        
        # Trade ledger (in-memory, would be DB in production)
        self._trade_ledger: list = []
        
    def _get_signal_hash(self, signal: TradingViewSignal) -> str:
        """Generate hash for deduplication"""
        key = f"{signal.action}:{signal.symbol}:{signal.price}:{signal.timestamp}"
        return hashlib.md5(key.encode()).hexdigest()[:12]
        
    def _is_duplicate(self, signal_hash: str) -> bool:
        """Check if signal is a duplicate"""
        if signal_hash in self._recent_signals:
            return True
        self._recent_signals.append(signal_hash)
        return False
        
    def _is_stale(self, signal: TradingViewSignal) -> bool:
        """Check if signal is too old"""
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        age_ms = now_ms - signal.timestamp
        return age_ms > self.config.max_signal_age_ms
        
    def _validate_secret(self, signal: TradingViewSignal) -> bool:
        """Validate shared secret"""
        if not self.config.secret:
            return True  # No secret configured
        return signal.secret == self.config.secret
        
    async def process_signal(self, signal: TradingViewSignal) -> ProcessedSignal:
        """
        Process a signal through the full pipeline
        """
        signal_hash = self._get_signal_hash(signal)
        signal_id = f"SIG_{signal_hash}_{int(datetime.utcnow().timestamp())}"
        
        processed = ProcessedSignal(
            signal_id=signal_id,
            received_at=datetime.utcnow(),
            payload=signal
        )
        
        # Step 1: Validate secret
        if not self._validate_secret(signal):
            processed.execution_result = "rejected:invalid_secret"
            logger.warning(f"Signal {signal_id} rejected: invalid secret")
            return processed
            
        # Step 2: Check freshness
        if self._is_stale(signal):
            processed.execution_result = "rejected:stale"
            logger.warning(f"Signal {signal_id} rejected: stale signal")
            return processed
            
        # Step 3: Deduplicate
        if self._is_duplicate(signal_hash):
            processed.execution_result = "rejected:duplicate"
            logger.warning(f"Signal {signal_id} rejected: duplicate")
            return processed
            
        # Step 4: Build market context
        context = MarketContext(
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            current_price=signal.price,
            signal_direction=signal.action,
            entry_price=signal.price,
            stop_loss=signal.stop,
            take_profit=signal.target,
            atr=signal.atr,
            bias=signal.bias
        )
        
        # Step 5: LLM evaluation
        decision = await self.llm_evaluator.evaluate_signal(context)
        processed.decision = decision
        
        if decision.action == SignalAction.REJECT:
            processed.execution_result = f"rejected:llm:{decision.reasoning[:50]}"
            logger.info(f"Signal {signal_id} rejected by LLM: {decision.reasoning}")
            self._log_to_ledger(processed)
            return processed
            
        if decision.action == SignalAction.DEFER:
            processed.execution_result = f"deferred:{decision.reasoning[:50]}"
            logger.info(f"Signal {signal_id} deferred: {decision.reasoning}")
            self._log_to_ledger(processed)
            return processed
            
        # Step 6: Risk check
        can_trade, restriction = self.risk_manager.can_trade(
            current_time=datetime.utcnow(),
            current_price=signal.price,
            atr=signal.atr
        )
        
        if not can_trade:
            processed.execution_result = f"rejected:risk:{restriction.value if restriction else 'unknown'}"
            logger.info(f"Signal {signal_id} rejected by risk manager: {restriction}")
            self._log_to_ledger(processed)
            return processed
            
        # Step 7: Execute (or paper log)
        if self.config.paper_mode:
            processed.execution_result = "paper_trade"
            processed.order_id = f"PAPER_{signal_id}"
            logger.info(f"Signal {signal_id} approved (paper mode): {signal.action} @ {signal.price}")
        else:
            try:
                order_id = await self._execute_order(signal, decision)
                processed.order_id = order_id
                processed.execution_result = "executed"
                logger.info(f"Signal {signal_id} executed: order {order_id}")
            except Exception as e:
                processed.execution_result = f"execution_failed:{str(e)[:50]}"
                logger.error(f"Signal {signal_id} execution failed: {e}")
                
        self._log_to_ledger(processed)
        return processed
        
    async def _execute_order(
        self, 
        signal: TradingViewSignal, 
        decision: SignalDecision
    ) -> str:
        """Execute order through NinjaTrader"""
        if self._nt_connection is None:
            self._nt_connection = NinjaTraderConnection(
                host=self.config.nt_host,
                port=self.config.nt_port,
                account=self.config.nt_account
            )
            if not self._nt_connection.connect():
                raise Exception("Failed to connect to NinjaTrader")
            self._order_manager = OrderManager(self._nt_connection)
            
        # Use adjusted values from LLM if provided
        stop = decision.adjusted_stop or signal.stop
        target = decision.adjusted_target or signal.target
        quantity = decision.position_size_suggestion or 1
        
        if signal.action == "buy":
            success = self._order_manager.enter_long(
                instrument="MNQ 03-24",  # Would be dynamic in production
                quantity=quantity,
                stop_loss=stop,
                take_profit=target
            )
        else:
            success = self._order_manager.enter_short(
                instrument="MNQ 03-24",
                quantity=quantity,
                stop_loss=stop,
                take_profit=target
            )
            
        if not success:
            raise Exception("Order placement failed")
            
        return f"NT_{int(datetime.utcnow().timestamp())}"
        
    def _log_to_ledger(self, processed: ProcessedSignal):
        """
        Log signal to trade ledger
        
        Architecture note (from Miles Deutscher course description):
        "complete trade ledger" and "written lessons from losing trades"
        """
        entry = processed.to_log_entry()
        self._trade_ledger.append(entry)
        
        if self.config.log_all_signals:
            logger.info(f"Ledger entry: {json.dumps(entry, default=str)}")
            
    def get_trade_ledger(self) -> list:
        """Get all trade ledger entries"""
        return self._trade_ledger.copy()
        
    def get_statistics(self) -> Dict:
        """Get processing statistics"""
        total = len(self._trade_ledger)
        executed = sum(1 for t in self._trade_ledger if t.get("execution_result") in ["executed", "paper_trade"])
        rejected = sum(1 for t in self._trade_ledger if t.get("execution_result", "").startswith("rejected"))
        
        return {
            "total_signals": total,
            "executed": executed,
            "rejected": rejected,
            "paper_mode": self.config.paper_mode
        }


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

def create_app() -> FastAPI:
    """Create the webhook server FastAPI application"""
    
    config = WebhookConfig()
    processor = SignalProcessor(config)
    
    app = FastAPI(
        title="TradingView Webhook Server",
        description="Receives TradingView alerts, evaluates with LLM, and routes to NinjaTrader",
        version="1.0.0"
    )
    
    @app.get("/")
    async def root():
        return {
            "service": "TradingView Webhook Server",
            "paper_mode": config.paper_mode,
            "status": "running"
        }
        
    @app.get("/health")
    async def health():
        return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
        
    @app.post("/webhook", response_model=WebhookResponse)
    async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
        """
        Receive TradingView webhook alert
        
        Expected JSON body from Pine Script alert():
        {
            "action": "buy" | "sell",
            "symbol": "MNQ",
            "price": 18500.25,
            "stop": 18480.00,
            "target": 18540.50,
            "atr": 15.5,
            "bias": 1,
            "timestamp": 1699999999999,
            "secret": "your_shared_secret"
        }
        """
        try:
            body = await request.json()
            signal = TradingViewSignal(**body)
        except Exception as e:
            logger.error(f"Invalid webhook payload: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid payload: {str(e)}")
            
        # Process signal
        result = await processor.process_signal(signal)
        
        return WebhookResponse(
            status="processed",
            message=result.execution_result or "unknown",
            signal_id=result.signal_id,
            decision=result.decision.to_dict() if result.decision else None,
            order_id=result.order_id
        )
        
    @app.get("/ledger")
    async def get_ledger():
        """Get trade ledger entries"""
        return {"entries": processor.get_trade_ledger()}
        
    @app.get("/stats")
    async def get_stats():
        """Get processing statistics"""
        return processor.get_statistics()
        
    @app.post("/test")
    async def test_signal():
        """Send a test signal for debugging"""
        test_signal = TradingViewSignal(
            action="buy",
            symbol="MNQ",
            price=18500.0,
            stop=18480.0,
            target=18540.0,
            atr=15.0,
            bias=1,
            timestamp=int(datetime.utcnow().timestamp() * 1000),
            secret=config.secret
        )
        result = await processor.process_signal(test_signal)
        return {
            "test_result": result.to_log_entry()
        }
        
    return app


class WebhookServer:
    """Wrapper for running the webhook server"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.app = create_app()
        
    def run(self):
        """Run the webhook server"""
        import uvicorn
        logger.info(f"Starting webhook server on {self.host}:{self.port}")
        uvicorn.run(self.app, host=self.host, port=self.port)


if __name__ == "__main__":
    server = WebhookServer()
    server.run()
