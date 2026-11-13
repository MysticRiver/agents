"""Configuration settings for the trading bot"""
import os
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class TradingSettings(BaseSettings):
    """Trading bot configuration"""
    
    # NinjaTrader connection
    NT_HOST: str = Field(default="127.0.0.1", description="NinjaTrader host")
    NT_PORT: int = Field(default=36973, description="NinjaTrader ATI port")
    NT_ACCOUNT: str = Field(default="Sim101", description="Trading account")
    
    # Trading parameters
    INSTRUMENT: str = Field(default="MNQ 03-24", description="Trading instrument")
    INITIAL_CAPITAL: float = Field(default=10000.0, description="Starting capital")
    DATA_INTERVAL: str = Field(default="5m", description="Data interval for signals")
    CHECK_INTERVAL_SECONDS: int = Field(default=60, description="Signal check interval")
    
    # Risk management
    MAX_POSITION_SIZE: int = Field(default=3, description="Maximum contracts")
    RISK_PER_TRADE_PCT: float = Field(default=1.0, description="Risk per trade %")
    MAX_DAILY_LOSS: float = Field(default=500.0, description="Max daily loss $")
    MAX_DAILY_LOSS_PCT: float = Field(default=5.0, description="Max daily loss %")
    MAX_TRADES_PER_DAY: int = Field(default=10, description="Max trades per day")
    MAX_DRAWDOWN_PCT: float = Field(default=20.0, description="Max drawdown %")
    
    # Session times (Eastern Time)
    TRADING_START_HOUR: int = Field(default=9, description="Trading start hour")
    TRADING_START_MINUTE: int = Field(default=30, description="Trading start minute")
    TRADING_END_HOUR: int = Field(default=16, description="Trading end hour")
    TRADING_END_MINUTE: int = Field(default=0, description="Trading end minute")
    
    # Strategy selection
    STRATEGY_NAME: str = Field(default="MA_Crossover", description="Strategy to use")
    STRATEGY_PARAMS: Optional[str] = Field(default=None, description="Strategy params JSON")
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    LOG_FILE: str = Field(default="logs/trading_bot.log", description="Log file path")
    
    # API endpoints for monitoring
    API_HOST: str = Field(default="0.0.0.0", description="API host")
    API_PORT: int = Field(default=8080, description="API port")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class BacktestSettings(BaseSettings):
    """Backtest configuration"""
    
    START_DATE: str = Field(default="2024-01-01", description="Backtest start date")
    END_DATE: Optional[str] = Field(default=None, description="Backtest end date")
    INITIAL_CAPITAL: float = Field(default=10000.0, description="Starting capital")
    DATA_INTERVAL: str = Field(default="5m", description="Data interval")
    COMMISSION_PER_CONTRACT: float = Field(default=0.50, description="Commission $")
    SLIPPAGE_TICKS: float = Field(default=1.0, description="Slippage in ticks")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_trading_settings() -> TradingSettings:
    """Get trading settings instance"""
    return TradingSettings()


def get_backtest_settings() -> BacktestSettings:
    """Get backtest settings instance"""
    return BacktestSettings()
