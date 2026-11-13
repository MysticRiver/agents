#!/usr/bin/env python3
"""
MNQ Trading Bot - Main Entry Point

This script starts the trading bot with the configured strategy
and provides a REST API for monitoring and control.
"""
import sys
import json
import signal
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from loguru import logger
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from config.settings import get_trading_settings
from src.bot import TradingBot, BotState
from src.risk.manager import RiskConfig

# Import strategies
from src.strategies.momentum import MACrossoverStrategy, BreakoutStrategy, MACDMomentumStrategy
from src.strategies.mean_reversion import RSIMeanReversionStrategy, BollingerBandStrategy
from src.strategies.volatility import ATRBreakoutStrategy, RangeExpansionStrategy
from src.strategies.time_based import OpeningRangeBreakoutStrategy, SessionMomentumStrategy

# Prometheus metrics
TRADES_TOTAL = Counter('trading_bot_trades_total', 'Total number of trades', ['direction'])
SIGNALS_TOTAL = Counter('trading_bot_signals_total', 'Total signals generated')
CURRENT_POSITION = Gauge('trading_bot_position', 'Current position size')
DAILY_PNL = Gauge('trading_bot_daily_pnl', 'Daily P&L in dollars')
BOT_STATUS = Gauge('trading_bot_status', 'Bot status (1=running, 0=stopped)')

# Configure logging
settings = get_trading_settings()
logger.remove()
logger.add(sys.stdout, level=settings.LOG_LEVEL)
logger.add(settings.LOG_FILE, level="DEBUG", rotation="10 MB")

# FastAPI app
app = FastAPI(
    title="MNQ Trading Bot API",
    description="REST API for monitoring and controlling the MNQ trading bot",
    version="1.0.0"
)

# Global bot instance
bot: Optional[TradingBot] = None


def get_strategy(strategy_name: str, params: Optional[dict] = None):
    """Get strategy instance by name"""
    params = params or {}
    
    strategies = {
        "MA_Crossover": MACrossoverStrategy,
        "Breakout": BreakoutStrategy,
        "MACD_Momentum": MACDMomentumStrategy,
        "RSI_MeanReversion": RSIMeanReversionStrategy,
        "BollingerBand_MeanReversion": BollingerBandStrategy,
        "ATR_Breakout": ATRBreakoutStrategy,
        "Range_Expansion": RangeExpansionStrategy,
        "Opening_Range_Breakout": OpeningRangeBreakoutStrategy,
        "Session_Momentum": SessionMomentumStrategy,
    }
    
    if strategy_name not in strategies:
        raise ValueError(f"Unknown strategy: {strategy_name}. Available: {list(strategies.keys())}")
    
    return strategies[strategy_name](**params)


def setup_bot():
    """Initialize the trading bot"""
    global bot
    
    # Load strategy configuration
    strategy_params = {}
    if settings.STRATEGY_PARAMS:
        try:
            strategy_params = json.loads(settings.STRATEGY_PARAMS)
        except json.JSONDecodeError:
            logger.warning("Failed to parse STRATEGY_PARAMS, using defaults")
    
    # Try to load best strategy from backtest results
    best_config_path = Path("results/best_strategy_config.json")
    if best_config_path.exists() and not strategy_params:
        try:
            with open(best_config_path) as f:
                config = json.load(f)
                strategy_name = config.get("strategy_name", settings.STRATEGY_NAME)
                strategy_params = config.get("parameters", {})
                logger.info(f"Loaded best strategy from backtest: {strategy_name}")
        except Exception as e:
            logger.warning(f"Failed to load best strategy config: {e}")
            strategy_name = settings.STRATEGY_NAME
    else:
        strategy_name = settings.STRATEGY_NAME
    
    # Create strategy
    strategy = get_strategy(strategy_name, strategy_params)
    logger.info(f"Using strategy: {strategy.name} with params: {strategy.parameters}")
    
    # Create risk config
    risk_config = RiskConfig(
        max_position_size=settings.MAX_POSITION_SIZE,
        risk_per_trade_pct=settings.RISK_PER_TRADE_PCT,
        max_daily_loss=settings.MAX_DAILY_LOSS,
        max_daily_loss_pct=settings.MAX_DAILY_LOSS_PCT,
        max_trades_per_day=settings.MAX_TRADES_PER_DAY,
        max_drawdown_pct=settings.MAX_DRAWDOWN_PCT
    )
    
    # Create bot
    bot = TradingBot(
        strategy=strategy,
        risk_config=risk_config,
        nt_host=settings.NT_HOST,
        nt_port=settings.NT_PORT,
        nt_account=settings.NT_ACCOUNT,
        initial_capital=settings.INITIAL_CAPITAL,
        data_interval=settings.DATA_INTERVAL,
        check_interval_seconds=settings.CHECK_INTERVAL_SECONDS
    )
    
    # Set callbacks for metrics
    def on_trade(signal, quantity, price):
        direction = "long" if signal == 1 else "short"
        TRADES_TOTAL.labels(direction=direction).inc()
        CURRENT_POSITION.set(bot._current_position)
        logger.info(f"Trade executed: {direction} {quantity} @ {price}")
    
    def on_signal(signal, price):
        SIGNALS_TOTAL.inc()
    
    bot.set_on_trade_callback(on_trade)
    bot.set_on_signal_callback(on_signal)
    
    return bot


# API Routes
@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "MNQ Trading Bot",
        "version": "1.0.0",
        "status": bot.state.value if bot else "not_initialized"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    if bot is None:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "reason": "bot_not_initialized"}
        )
    
    connected = bot.nt_connection.is_connected if bot.nt_connection else False
    
    return {
        "status": "healthy" if bot.state == BotState.RUNNING else "degraded",
        "bot_state": bot.state.value,
        "nt_connected": connected,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/status")
async def status():
    """Get detailed bot status"""
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    stats = bot.get_stats()
    return {
        "status": stats,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/start")
async def start_bot():
    """Start the trading bot"""
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    if bot.state == BotState.RUNNING:
        return {"message": "Bot is already running"}
    
    bot.start()
    BOT_STATUS.set(1)
    
    return {"message": "Bot started", "state": bot.state.value}


@app.post("/stop")
async def stop_bot():
    """Stop the trading bot"""
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    bot.stop()
    BOT_STATUS.set(0)
    
    return {"message": "Bot stopped", "state": bot.state.value}


@app.post("/pause")
async def pause_bot():
    """Pause the trading bot"""
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    bot.pause()
    
    return {"message": "Bot paused", "state": bot.state.value}


@app.post("/resume")
async def resume_bot():
    """Resume the trading bot"""
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    bot.resume()
    
    return {"message": "Bot resumed", "state": bot.state.value}


@app.get("/position")
async def get_position():
    """Get current position"""
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    return {
        "position": bot._current_position,
        "instrument": settings.INSTRUMENT
    }


@app.post("/flatten")
async def flatten_position():
    """Close all positions"""
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    if bot.order_manager:
        bot.order_manager.close_position(settings.INSTRUMENT)
        return {"message": "Position flattened"}
    
    raise HTTPException(status_code=503, detail="Order manager not available")


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


@app.get("/strategy")
async def get_strategy_info():
    """Get current strategy information"""
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    return {
        "name": bot.strategy.name,
        "parameters": bot.strategy.parameters
    }


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info("Shutdown signal received")
    if bot:
        bot.stop()
    sys.exit(0)


def main():
    """Main entry point"""
    global bot
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("="*60)
    logger.info("MNQ Trading Bot Starting")
    logger.info("="*60)
    
    # Setup bot
    bot = setup_bot()
    
    # Initialize
    if not bot.initialize():
        logger.error("Failed to initialize bot")
        sys.exit(1)
    
    # Start bot
    bot.start()
    BOT_STATUS.set(1)
    
    logger.info(f"API server starting on {settings.API_HOST}:{settings.API_PORT}")
    
    # Run API server
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="warning"
    )


if __name__ == "__main__":
    main()
