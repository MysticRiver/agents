"""Momentum and trend-following strategies"""
import pandas as pd
import numpy as np
from .base import BaseStrategy
from loguru import logger


class MACrossoverStrategy(BaseStrategy):
    """
    Moving Average Crossover Strategy
    
    Buy when fast MA crosses above slow MA
    Sell when fast MA crosses below slow MA
    
    Uses EMA for faster response to price changes.
    Optional trend filter with longer-term MA.
    """
    
    def __init__(
        self,
        fast_period: int = 9,
        slow_period: int = 21,
        trend_period: int = 50,
        use_trend_filter: bool = True,
        atr_stop_multiplier: float = 2.0,
        atr_target_multiplier: float = 3.0
    ):
        super().__init__(
            name="MA_Crossover",
            fast_period=fast_period,
            slow_period=slow_period,
            trend_period=trend_period,
            use_trend_filter=use_trend_filter,
            atr_stop_multiplier=atr_stop_multiplier,
            atr_target_multiplier=atr_target_multiplier
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.trend_period = trend_period
        self.use_trend_filter = use_trend_filter
        self.atr_stop_multiplier = atr_stop_multiplier
        self.atr_target_multiplier = atr_target_multiplier
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate trading signals based on MA crossover"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # Calculate moving averages
        df["EMA_Fast"] = self.calculate_ema(df["Close"], self.fast_period)
        df["EMA_Slow"] = self.calculate_ema(df["Close"], self.slow_period)
        df["EMA_Trend"] = self.calculate_ema(df["Close"], self.trend_period)
        df["ATR"] = self.calculate_atr(df, 14)
        
        # Initialize signals
        df["Signal"] = 0
        
        # Generate crossover signals
        df["Cross"] = 0
        df.loc[df["EMA_Fast"] > df["EMA_Slow"], "Cross"] = 1
        df.loc[df["EMA_Fast"] < df["EMA_Slow"], "Cross"] = -1
        
        # Detect crossover events
        df["CrossChange"] = df["Cross"].diff()
        
        # Apply trend filter if enabled
        if self.use_trend_filter:
            # Buy only in uptrend (price above trend EMA)
            buy_condition = (df["CrossChange"] == 2) & (df["Close"] > df["EMA_Trend"])
            # Sell only in downtrend (price below trend EMA)
            sell_condition = (df["CrossChange"] == -2) & (df["Close"] < df["EMA_Trend"])
        else:
            buy_condition = df["CrossChange"] == 2
            sell_condition = df["CrossChange"] == -2
        
        df.loc[buy_condition, "Signal"] = 1
        df.loc[sell_condition, "Signal"] = -1
        
        # Calculate stop loss and take profit levels
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        # For buy signals
        df.loc[df["Signal"] == 1, "StopLoss"] = df["Close"] - (df["ATR"] * self.atr_stop_multiplier)
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["Close"] + (df["ATR"] * self.atr_target_multiplier)
        
        # For sell signals
        df.loc[df["Signal"] == -1, "StopLoss"] = df["Close"] + (df["ATR"] * self.atr_stop_multiplier)
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["Close"] - (df["ATR"] * self.atr_target_multiplier)
        
        # Forward fill stop/target for position management
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        return df


class BreakoutStrategy(BaseStrategy):
    """
    Donchian Channel Breakout Strategy
    
    Buy when price breaks above the N-period high
    Sell when price breaks below the N-period low
    
    Classic trend-following approach used by Turtle Traders.
    """
    
    def __init__(
        self,
        entry_period: int = 20,
        exit_period: int = 10,
        atr_period: int = 14,
        atr_stop_multiplier: float = 2.0,
        volume_filter: bool = True,
        volume_threshold: float = 1.2
    ):
        super().__init__(
            name="Breakout",
            entry_period=entry_period,
            exit_period=exit_period,
            atr_period=atr_period,
            atr_stop_multiplier=atr_stop_multiplier,
            volume_filter=volume_filter,
            volume_threshold=volume_threshold
        )
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.atr_stop_multiplier = atr_stop_multiplier
        self.volume_filter = volume_filter
        self.volume_threshold = volume_threshold
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on price breakouts"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # Calculate Donchian Channels
        df["Entry_High"] = df["High"].rolling(window=self.entry_period).max()
        df["Entry_Low"] = df["Low"].rolling(window=self.entry_period).min()
        df["Exit_High"] = df["High"].rolling(window=self.exit_period).max()
        df["Exit_Low"] = df["Low"].rolling(window=self.exit_period).min()
        
        # Calculate ATR for stops
        df["ATR"] = self.calculate_atr(df, self.atr_period)
        
        # Volume filter
        df["Volume_SMA"] = df["Volume"].rolling(window=20).mean()
        df["Volume_Ratio"] = df["Volume"] / df["Volume_SMA"]
        
        # Initialize signals
        df["Signal"] = 0
        
        # Shift channels to avoid lookahead bias
        entry_high_prev = df["Entry_High"].shift(1)
        entry_low_prev = df["Entry_Low"].shift(1)
        exit_high_prev = df["Exit_High"].shift(1)
        exit_low_prev = df["Exit_Low"].shift(1)
        
        # Breakout conditions
        long_breakout = df["Close"] > entry_high_prev
        short_breakout = df["Close"] < entry_low_prev
        
        # Exit conditions (opposite channel)
        long_exit = df["Close"] < exit_low_prev
        short_exit = df["Close"] > exit_high_prev
        
        # Apply volume filter if enabled
        if self.volume_filter:
            volume_ok = df["Volume_Ratio"] > self.volume_threshold
            long_breakout = long_breakout & volume_ok
            short_breakout = short_breakout & volume_ok
        
        # Track position state to generate proper signals
        position = 0
        signals = []
        
        for i in range(len(df)):
            signal = 0
            
            if position == 0:  # No position
                if long_breakout.iloc[i]:
                    signal = 1
                    position = 1
                elif short_breakout.iloc[i]:
                    signal = -1
                    position = -1
            elif position == 1:  # Long position
                if long_exit.iloc[i] or short_breakout.iloc[i]:
                    signal = -1 if short_breakout.iloc[i] else 0
                    position = -1 if short_breakout.iloc[i] else 0
            elif position == -1:  # Short position
                if short_exit.iloc[i] or long_breakout.iloc[i]:
                    signal = 1 if long_breakout.iloc[i] else 0
                    position = 1 if long_breakout.iloc[i] else 0
            
            signals.append(signal)
        
        df["Signal"] = signals
        
        # Stop loss levels
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        df.loc[df["Signal"] == 1, "StopLoss"] = df["Close"] - (df["ATR"] * self.atr_stop_multiplier)
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["Close"] + (df["ATR"] * self.atr_stop_multiplier * 2)
        
        df.loc[df["Signal"] == -1, "StopLoss"] = df["Close"] + (df["ATR"] * self.atr_stop_multiplier)
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["Close"] - (df["ATR"] * self.atr_stop_multiplier * 2)
        
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        return df


class MACDMomentumStrategy(BaseStrategy):
    """
    MACD Momentum Strategy
    
    Uses MACD crossovers with histogram confirmation.
    Requires momentum alignment for entry.
    """
    
    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        histogram_threshold: float = 0.5,
        require_histogram_confirmation: bool = True
    ):
        super().__init__(
            name="MACD_Momentum",
            fast_period=fast_period,
            slow_period=slow_period,
            signal_period=signal_period,
            histogram_threshold=histogram_threshold,
            require_histogram_confirmation=require_histogram_confirmation
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.histogram_threshold = histogram_threshold
        self.require_histogram_confirmation = require_histogram_confirmation
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on MACD"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # Calculate MACD
        macd, signal, histogram = self.calculate_macd(
            df["Close"], 
            self.fast_period, 
            self.slow_period, 
            self.signal_period
        )
        
        df["MACD"] = macd
        df["MACD_Signal"] = signal
        df["MACD_Hist"] = histogram
        df["ATR"] = self.calculate_atr(df, 14)
        
        # Initialize signals
        df["Signal"] = 0
        
        # MACD crossover
        macd_cross_up = (df["MACD"] > df["MACD_Signal"]) & (df["MACD"].shift(1) <= df["MACD_Signal"].shift(1))
        macd_cross_down = (df["MACD"] < df["MACD_Signal"]) & (df["MACD"].shift(1) >= df["MACD_Signal"].shift(1))
        
        if self.require_histogram_confirmation:
            # Require histogram to be above threshold
            hist_bullish = df["MACD_Hist"] > self.histogram_threshold
            hist_bearish = df["MACD_Hist"] < -self.histogram_threshold
            
            buy_signal = macd_cross_up & (hist_bullish | (df["MACD_Hist"].shift(1) < 0))
            sell_signal = macd_cross_down & (hist_bearish | (df["MACD_Hist"].shift(1) > 0))
        else:
            buy_signal = macd_cross_up
            sell_signal = macd_cross_down
        
        df.loc[buy_signal, "Signal"] = 1
        df.loc[sell_signal, "Signal"] = -1
        
        # Stop loss and take profit
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        df.loc[df["Signal"] == 1, "StopLoss"] = df["Close"] - (df["ATR"] * 2)
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["Close"] + (df["ATR"] * 3)
        
        df.loc[df["Signal"] == -1, "StopLoss"] = df["Close"] + (df["ATR"] * 2)
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["Close"] - (df["ATR"] * 3)
        
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        return df
