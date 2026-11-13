"""Time-based trading strategies"""
import pandas as pd
import numpy as np
from .base import BaseStrategy
from loguru import logger


class OpeningRangeBreakoutStrategy(BaseStrategy):
    """
    Opening Range Breakout (ORB) Strategy
    
    Identifies the high/low of the first N minutes of the session.
    Enters when price breaks out of this range.
    
    Classic intraday strategy for index futures.
    """
    
    def __init__(
        self,
        opening_range_minutes: int = 30,
        session_start_hour: int = 9,
        session_start_minute: int = 30,
        session_end_hour: int = 16,
        session_end_minute: int = 0,
        require_volume_confirmation: bool = True,
        volume_multiplier: float = 1.3,
        atr_stop_multiplier: float = 1.0,
        range_extension_target: float = 1.5,
        max_trades_per_day: int = 2
    ):
        super().__init__(
            name="Opening_Range_Breakout",
            opening_range_minutes=opening_range_minutes,
            session_start_hour=session_start_hour,
            session_start_minute=session_start_minute,
            session_end_hour=session_end_hour,
            session_end_minute=session_end_minute,
            require_volume_confirmation=require_volume_confirmation,
            volume_multiplier=volume_multiplier,
            atr_stop_multiplier=atr_stop_multiplier,
            range_extension_target=range_extension_target,
            max_trades_per_day=max_trades_per_day
        )
        self.opening_range_minutes = opening_range_minutes
        self.session_start_hour = session_start_hour
        self.session_start_minute = session_start_minute
        self.session_end_hour = session_end_hour
        self.session_end_minute = session_end_minute
        self.require_volume_confirmation = require_volume_confirmation
        self.volume_multiplier = volume_multiplier
        self.atr_stop_multiplier = atr_stop_multiplier
        self.range_extension_target = range_extension_target
        self.max_trades_per_day = max_trades_per_day
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on opening range breakout"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # ATR for stops
        df["ATR"] = self.calculate_atr(df, 14)
        
        # Volume metrics
        df["Volume_SMA"] = df["Volume"].rolling(window=20).mean()
        df["Volume_Ratio"] = df["Volume"] / df["Volume_SMA"]
        
        # Extract time components
        df["Hour"] = df.index.hour
        df["Minute"] = df.index.minute
        df["Date"] = df.index.date
        
        # Identify session boundaries
        session_start = self.session_start_hour * 60 + self.session_start_minute
        or_end = session_start + self.opening_range_minutes
        session_end = self.session_end_hour * 60 + self.session_end_minute
        
        df["Minutes"] = df["Hour"] * 60 + df["Minute"]
        df["In_OR_Period"] = (df["Minutes"] >= session_start) & (df["Minutes"] < or_end)
        df["In_Trading_Window"] = (df["Minutes"] >= or_end) & (df["Minutes"] < session_end - 30)
        
        # Calculate opening range for each day
        df["OR_High"] = np.nan
        df["OR_Low"] = np.nan
        
        for date in df["Date"].unique():
            mask = df["Date"] == date
            or_mask = mask & df["In_OR_Period"]
            
            if or_mask.any():
                or_high = df.loc[or_mask, "High"].max()
                or_low = df.loc[or_mask, "Low"].min()
                
                # Apply to entire day after OR period
                trading_mask = mask & df["In_Trading_Window"]
                df.loc[trading_mask, "OR_High"] = or_high
                df.loc[trading_mask, "OR_Low"] = or_low
        
        # Opening range size
        df["OR_Range"] = df["OR_High"] - df["OR_Low"]
        
        # Initialize signals
        df["Signal"] = 0
        
        # Track trades per day
        trades_today = {}
        signals = []
        
        for idx, row in df.iterrows():
            signal = 0
            date = row["Date"]
            
            if date not in trades_today:
                trades_today[date] = 0
            
            # Only trade in trading window
            if row["In_Trading_Window"] and trades_today[date] < self.max_trades_per_day:
                or_high = row["OR_High"]
                or_low = row["OR_Low"]
                close = row["Close"]
                
                if pd.notna(or_high) and pd.notna(or_low):
                    # Long breakout
                    if close > or_high:
                        if not self.require_volume_confirmation or row["Volume_Ratio"] > self.volume_multiplier:
                            signal = 1
                            trades_today[date] += 1
                    # Short breakout
                    elif close < or_low:
                        if not self.require_volume_confirmation or row["Volume_Ratio"] > self.volume_multiplier:
                            signal = -1
                            trades_today[date] += 1
            
            signals.append(signal)
        
        df["Signal"] = signals
        
        # Stop loss and take profit
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        # For longs: stop at OR low, target at extension
        or_range = df["OR_High"] - df["OR_Low"]
        df.loc[df["Signal"] == 1, "StopLoss"] = df["OR_Low"] - (df["ATR"] * self.atr_stop_multiplier)
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["OR_High"] + (or_range * self.range_extension_target)
        
        # For shorts: stop at OR high, target at extension
        df.loc[df["Signal"] == -1, "StopLoss"] = df["OR_High"] + (df["ATR"] * self.atr_stop_multiplier)
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["OR_Low"] - (or_range * self.range_extension_target)
        
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        # Clean up temporary columns
        df = df.drop(columns=["Hour", "Minute", "Date", "Minutes", "In_OR_Period", "In_Trading_Window"])
        
        return df


class SessionMomentumStrategy(BaseStrategy):
    """
    Session Momentum Strategy
    
    Trades based on momentum established in early session.
    If market opens strong, trade with the trend.
    
    Uses first hour performance to determine bias.
    """
    
    def __init__(
        self,
        momentum_period_minutes: int = 60,
        session_start_hour: int = 9,
        session_start_minute: int = 30,
        session_end_hour: int = 15,
        momentum_threshold_pct: float = 0.3,
        use_vwap: bool = True,
        atr_stop_multiplier: float = 2.0,
        atr_target_multiplier: float = 3.0
    ):
        super().__init__(
            name="Session_Momentum",
            momentum_period_minutes=momentum_period_minutes,
            session_start_hour=session_start_hour,
            session_start_minute=session_start_minute,
            session_end_hour=session_end_hour,
            momentum_threshold_pct=momentum_threshold_pct,
            use_vwap=use_vwap,
            atr_stop_multiplier=atr_stop_multiplier,
            atr_target_multiplier=atr_target_multiplier
        )
        self.momentum_period_minutes = momentum_period_minutes
        self.session_start_hour = session_start_hour
        self.session_start_minute = session_start_minute
        self.session_end_hour = session_end_hour
        self.momentum_threshold_pct = momentum_threshold_pct
        self.use_vwap = use_vwap
        self.atr_stop_multiplier = atr_stop_multiplier
        self.atr_target_multiplier = atr_target_multiplier
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on session momentum"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # ATR for stops
        df["ATR"] = self.calculate_atr(df, 14)
        
        # Time components
        df["Hour"] = df.index.hour
        df["Minute"] = df.index.minute
        df["Date"] = df.index.date
        df["Minutes"] = df["Hour"] * 60 + df["Minute"]
        
        session_start = self.session_start_hour * 60 + self.session_start_minute
        momentum_end = session_start + self.momentum_period_minutes
        session_end = self.session_end_hour * 60
        
        df["In_Momentum_Period"] = (df["Minutes"] >= session_start) & (df["Minutes"] < momentum_end)
        df["In_Trading_Window"] = (df["Minutes"] >= momentum_end) & (df["Minutes"] < session_end - 30)
        
        # Calculate VWAP if enabled
        if self.use_vwap:
            df["Typical_Price"] = (df["High"] + df["Low"] + df["Close"]) / 3
            df["VWAP_Num"] = np.nan
            df["VWAP_Den"] = np.nan
            df["VWAP"] = np.nan
            
            for date in df["Date"].unique():
                mask = df["Date"] == date
                df.loc[mask, "VWAP_Num"] = (df.loc[mask, "Typical_Price"] * df.loc[mask, "Volume"]).cumsum()
                df.loc[mask, "VWAP_Den"] = df.loc[mask, "Volume"].cumsum()
            
            df["VWAP"] = df["VWAP_Num"] / df["VWAP_Den"]
        
        # Calculate momentum metrics for each day
        df["Session_Open"] = np.nan
        df["Momentum_Change"] = np.nan
        df["Momentum_Bias"] = 0
        
        for date in df["Date"].unique():
            mask = df["Date"] == date
            momentum_mask = mask & df["In_Momentum_Period"]
            
            if momentum_mask.any():
                session_open = df.loc[momentum_mask, "Open"].iloc[0]
                momentum_close = df.loc[momentum_mask, "Close"].iloc[-1]
                momentum_change = (momentum_close - session_open) / session_open * 100
                
                # Determine bias
                if momentum_change > self.momentum_threshold_pct:
                    bias = 1  # Bullish
                elif momentum_change < -self.momentum_threshold_pct:
                    bias = -1  # Bearish
                else:
                    bias = 0  # Neutral
                
                # Apply to trading window
                trading_mask = mask & df["In_Trading_Window"]
                df.loc[trading_mask, "Session_Open"] = session_open
                df.loc[trading_mask, "Momentum_Change"] = momentum_change
                df.loc[trading_mask, "Momentum_Bias"] = bias
        
        # Initialize signals
        df["Signal"] = 0
        
        # Generate signals based on bias and price action
        for idx, row in df.iterrows():
            if not row["In_Trading_Window"]:
                continue
                
            bias = row["Momentum_Bias"]
            
            if bias == 0:  # No trade in neutral conditions
                continue
            
            # For bullish bias: buy on pullbacks to VWAP or trend continuation
            if bias == 1:
                if self.use_vwap and pd.notna(row["VWAP"]):
                    # Buy when price pulls back to VWAP and bounces
                    if row["Low"] <= row["VWAP"] * 1.001 and row["Close"] > row["VWAP"]:
                        df.loc[idx, "Signal"] = 1
                else:
                    # Simple momentum continuation
                    if row["Close"] > row["Open"]:
                        df.loc[idx, "Signal"] = 1
            
            # For bearish bias: sell on rallies to VWAP
            elif bias == -1:
                if self.use_vwap and pd.notna(row["VWAP"]):
                    # Sell when price rallies to VWAP and fails
                    if row["High"] >= row["VWAP"] * 0.999 and row["Close"] < row["VWAP"]:
                        df.loc[idx, "Signal"] = -1
                else:
                    # Simple momentum continuation
                    if row["Close"] < row["Open"]:
                        df.loc[idx, "Signal"] = -1
        
        # Stop loss and take profit
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        df.loc[df["Signal"] == 1, "StopLoss"] = df["Close"] - (df["ATR"] * self.atr_stop_multiplier)
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["Close"] + (df["ATR"] * self.atr_target_multiplier)
        
        df.loc[df["Signal"] == -1, "StopLoss"] = df["Close"] + (df["ATR"] * self.atr_stop_multiplier)
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["Close"] - (df["ATR"] * self.atr_target_multiplier)
        
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        # Clean up
        cols_to_drop = ["Hour", "Minute", "Date", "Minutes", "In_Momentum_Period", "In_Trading_Window"]
        if self.use_vwap:
            cols_to_drop.extend(["Typical_Price", "VWAP_Num", "VWAP_Den"])
        df = df.drop(columns=[c for c in cols_to_drop if c in df.columns])
        
        return df


class LondonOpenStrategy(BaseStrategy):
    """
    London Open Strategy (adapted for US futures)
    
    Trades the momentum from European session into US open.
    Looks for continuation or reversal patterns at the open.
    """
    
    def __init__(
        self,
        pre_market_start_hour: int = 4,  # 4 AM ET (London open)
        us_open_hour: int = 9,
        us_open_minute: int = 30,
        trading_window_hours: int = 2,
        min_pre_market_move_pct: float = 0.2,
        continuation_mode: bool = True
    ):
        super().__init__(
            name="London_Open",
            pre_market_start_hour=pre_market_start_hour,
            us_open_hour=us_open_hour,
            us_open_minute=us_open_minute,
            trading_window_hours=trading_window_hours,
            min_pre_market_move_pct=min_pre_market_move_pct,
            continuation_mode=continuation_mode
        )
        self.pre_market_start_hour = pre_market_start_hour
        self.us_open_hour = us_open_hour
        self.us_open_minute = us_open_minute
        self.trading_window_hours = trading_window_hours
        self.min_pre_market_move_pct = min_pre_market_move_pct
        self.continuation_mode = continuation_mode
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on London session momentum"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # ATR for stops
        df["ATR"] = self.calculate_atr(df, 14)
        
        # Time components
        df["Hour"] = df.index.hour
        df["Minute"] = df.index.minute
        df["Date"] = df.index.date
        df["Minutes"] = df["Hour"] * 60 + df["Minute"]
        
        pre_market_start = self.pre_market_start_hour * 60
        us_open = self.us_open_hour * 60 + self.us_open_minute
        trading_end = us_open + (self.trading_window_hours * 60)
        
        df["In_Pre_Market"] = (df["Minutes"] >= pre_market_start) & (df["Minutes"] < us_open)
        df["In_Trading_Window"] = (df["Minutes"] >= us_open) & (df["Minutes"] < trading_end)
        
        # Calculate pre-market momentum for each day
        df["Pre_Market_Move"] = np.nan
        df["Pre_Market_Bias"] = 0
        
        for date in df["Date"].unique():
            mask = df["Date"] == date
            pre_market_mask = mask & df["In_Pre_Market"]
            
            if pre_market_mask.any():
                pm_open = df.loc[pre_market_mask, "Open"].iloc[0]
                pm_close = df.loc[pre_market_mask, "Close"].iloc[-1]
                pm_move = (pm_close - pm_open) / pm_open * 100
                
                if abs(pm_move) > self.min_pre_market_move_pct:
                    bias = 1 if pm_move > 0 else -1
                else:
                    bias = 0
                
                trading_mask = mask & df["In_Trading_Window"]
                df.loc[trading_mask, "Pre_Market_Move"] = pm_move
                df.loc[trading_mask, "Pre_Market_Bias"] = bias
        
        # Initialize signals
        df["Signal"] = 0
        
        # Generate signals at US open based on pre-market bias
        for date in df["Date"].unique():
            mask = (df["Date"] == date) & df["In_Trading_Window"]
            if not mask.any():
                continue
                
            first_bar = df.loc[mask].index[0]
            bias = df.loc[first_bar, "Pre_Market_Bias"]
            
            if bias == 0:
                continue
            
            if self.continuation_mode:
                # Trade with pre-market momentum
                df.loc[first_bar, "Signal"] = bias
            else:
                # Fade pre-market momentum (reversal)
                df.loc[first_bar, "Signal"] = -bias
        
        # Stop loss and take profit
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        df.loc[df["Signal"] == 1, "StopLoss"] = df["Close"] - (df["ATR"] * 2)
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["Close"] + (df["ATR"] * 3)
        
        df.loc[df["Signal"] == -1, "StopLoss"] = df["Close"] + (df["ATR"] * 2)
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["Close"] - (df["ATR"] * 3)
        
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        # Clean up
        df = df.drop(columns=["Hour", "Minute", "Date", "Minutes", "In_Pre_Market", "In_Trading_Window"])
        
        return df
