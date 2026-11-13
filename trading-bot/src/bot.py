"""Main trading bot orchestrator"""
import time
import threading
from datetime import datetime, time as dt_time
from typing import Optional, Dict, Any
from enum import Enum
from loguru import logger
import schedule

from .data.data_handler import DataHandler
from .strategies.base import BaseStrategy
from .broker.ninjatrader import NinjaTraderConnection, OrderManager, OrderAction, Position
from .risk.manager import RiskManager, RiskConfig


class BotState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


class TradingBot:
    """
    MNQ Futures Trading Bot
    
    Orchestrates data feed, strategy execution, risk management,
    and broker communication.
    """
    
    INSTRUMENT = "MNQ 03-24"  # Update with current contract
    
    def __init__(
        self,
        strategy: BaseStrategy,
        risk_config: Optional[RiskConfig] = None,
        nt_host: str = "127.0.0.1",
        nt_port: int = 36973,
        nt_account: str = "Sim101",
        initial_capital: float = 10000.0,
        data_interval: str = "1m",
        check_interval_seconds: int = 60
    ):
        self.strategy = strategy
        self.risk_config = risk_config or RiskConfig()
        self.initial_capital = initial_capital
        self.data_interval = data_interval
        self.check_interval = check_interval_seconds
        
        # Initialize components
        self.data_handler = DataHandler()
        self.risk_manager = RiskManager(self.risk_config)
        
        # NinjaTrader connection
        self.nt_connection = NinjaTraderConnection(
            host=nt_host,
            port=nt_port,
            account=nt_account
        )
        self.order_manager: Optional[OrderManager] = None
        
        # State
        self._state = BotState.STOPPED
        self._current_position = 0
        self._last_signal = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Statistics
        self._stats = {
            "trades_today": 0,
            "pnl_today": 0.0,
            "signals_generated": 0,
            "last_check_time": None
        }
        
        # Callbacks
        self._on_trade: Optional[callable] = None
        self._on_signal: Optional[callable] = None
        self._on_error: Optional[callable] = None
        
    @property
    def state(self) -> BotState:
        return self._state
        
    def initialize(self) -> bool:
        """Initialize all components"""
        logger.info(f"Initializing trading bot with strategy: {self.strategy.name}")
        
        # Initialize risk manager
        self.risk_manager.initialize(self.initial_capital)
        
        # Connect to NinjaTrader
        if not self.nt_connection.connect():
            logger.error("Failed to connect to NinjaTrader")
            self._state = BotState.ERROR
            return False
            
        self.order_manager = OrderManager(self.nt_connection)
        
        # Subscribe to position updates
        self.nt_connection.subscribe_to_fills(self._on_fill)
        self.nt_connection.subscribe_to_positions(self._on_position_update)
        self.nt_connection.subscribe_to_errors(self._on_nt_error)
        
        logger.info("Trading bot initialized successfully")
        self._state = BotState.STOPPED
        return True
        
    def start(self):
        """Start the trading bot"""
        if self._state == BotState.RUNNING:
            logger.warning("Bot is already running")
            return
            
        if not self.nt_connection.is_connected:
            if not self.initialize():
                return
                
        self._running = True
        self._state = BotState.RUNNING
        
        # Start main loop in background thread
        self._thread = threading.Thread(target=self._main_loop, daemon=True)
        self._thread.start()
        
        logger.info("Trading bot started")
        
    def stop(self):
        """Stop the trading bot"""
        logger.info("Stopping trading bot...")
        self._running = False
        self._state = BotState.STOPPED
        
        # Close any open positions
        if self._current_position != 0:
            logger.info("Closing open positions before shutdown")
            self.order_manager.close_position(self.INSTRUMENT)
            
        # Disconnect
        self.nt_connection.disconnect()
        
        if self._thread:
            self._thread.join(timeout=5.0)
            
        logger.info("Trading bot stopped")
        
    def pause(self):
        """Pause trading (no new positions, but manage existing)"""
        self._state = BotState.PAUSED
        logger.info("Trading bot paused")
        
    def resume(self):
        """Resume trading"""
        if self._state == BotState.PAUSED:
            self._state = BotState.RUNNING
            logger.info("Trading bot resumed")
            
    def _main_loop(self):
        """Main trading loop"""
        while self._running:
            try:
                self._check_and_trade()
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                if self._on_error:
                    self._on_error(str(e))
                    
            time.sleep(self.check_interval)
            
    def _check_and_trade(self):
        """Check for signals and execute trades"""
        current_time = datetime.now()
        self._stats["last_check_time"] = current_time
        
        # Check if trading is allowed
        can_trade, restriction = self.risk_manager.can_trade(
            current_time=current_time,
            current_price=0.0  # Will get from data
        )
        
        if not can_trade:
            logger.debug(f"Trading restricted: {restriction}")
            
            # Still check for position close at session end
            should_close, _ = self.risk_manager.should_close_position(current_time)
            if should_close and self._current_position != 0:
                logger.info("Closing position at session end")
                self.order_manager.close_position(self.INSTRUMENT)
            return
            
        # Skip if paused
        if self._state == BotState.PAUSED:
            return
            
        # Get latest data
        data = self._get_latest_data()
        if data is None or data.empty:
            logger.warning("No data available")
            return
            
        # Add indicators
        data = self.data_handler.add_indicators(data)
        
        # Generate signals
        signals_df = self.strategy.generate_signals(data)
        latest_signal = signals_df["Signal"].iloc[-1]
        latest_price = signals_df["Close"].iloc[-1]
        
        self._stats["signals_generated"] += 1
        
        if self._on_signal:
            self._on_signal(latest_signal, latest_price)
            
        # Execute signal if different from current position
        if latest_signal != 0 and latest_signal != self._last_signal:
            self._execute_signal(
                signal=latest_signal,
                price=latest_price,
                signals_df=signals_df
            )
            self._last_signal = latest_signal
            
    def _get_latest_data(self, lookback_bars: int = 100):
        """Get latest price data"""
        try:
            from datetime import timedelta
            end_date = datetime.now()
            
            if self.data_interval == "1m":
                start_date = end_date - timedelta(hours=lookback_bars // 60 + 2)
            elif self.data_interval == "5m":
                start_date = end_date - timedelta(hours=lookback_bars * 5 // 60 + 2)
            else:
                start_date = end_date - timedelta(days=lookback_bars)
                
            data = self.data_handler.get_data(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                interval=self.data_interval
            )
            
            return data.tail(lookback_bars)
            
        except Exception as e:
            logger.error(f"Failed to get data: {e}")
            return None
            
    def _execute_signal(
        self,
        signal: int,
        price: float,
        signals_df
    ):
        """Execute a trading signal"""
        logger.info(f"Executing signal: {signal} at price {price:.2f}")
        
        # Get stop loss and take profit from strategy
        stop_loss = signals_df["StopLoss"].iloc[-1] if "StopLoss" in signals_df else None
        take_profit = signals_df["TakeProfit"].iloc[-1] if "TakeProfit" in signals_df else None
        
        # Calculate position size
        account_equity = self.initial_capital + self._stats["pnl_today"]
        
        if stop_loss and not pd.isna(stop_loss):
            position_size = self.risk_manager.calculate_position_size(
                account_equity=account_equity,
                entry_price=price,
                stop_loss=stop_loss,
                signal_direction=signal
            )
        else:
            position_size = 1  # Default to 1 contract
            
        if position_size == 0:
            logger.warning("Position size calculated as 0, skipping trade")
            return
            
        # Close existing position if opposite direction
        if self._current_position != 0:
            if (signal == 1 and self._current_position < 0) or \
               (signal == -1 and self._current_position > 0):
                logger.info("Closing existing position")
                self.order_manager.close_position(self.INSTRUMENT)
                self._current_position = 0
                
        # Enter new position
        if signal == 1:  # Long
            success = self.order_manager.enter_long(
                instrument=self.INSTRUMENT,
                quantity=position_size,
                stop_loss=stop_loss if stop_loss and not pd.isna(stop_loss) else None,
                take_profit=take_profit if take_profit and not pd.isna(take_profit) else None
            )
            if success:
                logger.info(f"Entered LONG {position_size} @ {price:.2f}")
                self._current_position = position_size
                
        elif signal == -1:  # Short
            success = self.order_manager.enter_short(
                instrument=self.INSTRUMENT,
                quantity=position_size,
                stop_loss=stop_loss if stop_loss and not pd.isna(stop_loss) else None,
                take_profit=take_profit if take_profit and not pd.isna(take_profit) else None
            )
            if success:
                logger.info(f"Entered SHORT {position_size} @ {price:.2f}")
                self._current_position = -position_size
                
        self._stats["trades_today"] += 1
        self.risk_manager.set_position(self._current_position)
        
        if self._on_trade:
            self._on_trade(signal, position_size, price)
            
    def _on_fill(self, order):
        """Handle order fill notification"""
        logger.info(f"Order filled: {order.order_id} @ {order.fill_price}")
        
    def _on_position_update(self, position: Position):
        """Handle position update from broker"""
        self._current_position = position.quantity
        logger.info(f"Position update: {position.quantity} @ {position.avg_price}")
        
    def _on_nt_error(self, error: str):
        """Handle NinjaTrader error"""
        logger.error(f"NinjaTrader error: {error}")
        if self._on_error:
            self._on_error(error)
            
    def get_stats(self) -> Dict[str, Any]:
        """Get current bot statistics"""
        return {
            **self._stats,
            "state": self._state.value,
            "strategy": self.strategy.name,
            "current_position": self._current_position,
            "connected": self.nt_connection.is_connected,
            "risk_stats": self.risk_manager.get_stats()
        }
        
    def set_on_trade_callback(self, callback: callable):
        """Set callback for trade execution"""
        self._on_trade = callback
        
    def set_on_signal_callback(self, callback: callable):
        """Set callback for signal generation"""
        self._on_signal = callback
        
    def set_on_error_callback(self, callback: callable):
        """Set callback for errors"""
        self._on_error = callback


# Convenience import for missing pd
import pandas as pd
