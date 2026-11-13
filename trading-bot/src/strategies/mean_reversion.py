"""Mean reversion strategies"""
import pandas as pd
import numpy as np
from .base import BaseStrategy
from loguru import logger


class RSIMeanReversionStrategy(BaseStrategy):
    """
    RSI Mean Reversion Strategy
    
    Buy when RSI is oversold and starts recovering
    Sell when RSI is overbought and starts declining
    
    Uses confirmation from price action to avoid catching falling knives.
    """
    
    def __init__(
        self,
        rsi_period: int = 14,
        oversold_level: int = 30,
        overbought_level: int = 70,
        exit_level: int = 50,
        use_divergence: bool = False,
        require_reversal_candle: bool = True,
        atr_stop_multiplier: float = 1.5,
        atr_target_multiplier: float = 2.5
    ):
        super().__init__(
            name="RSI_MeanReversion",
            rsi_period=rsi_period,
            oversold_level=oversold_level,
            overbought_level=overbought_level,
            exit_level=exit_level,
            use_divergence=use_divergence,
            require_reversal_candle=require_reversal_candle,
            atr_stop_multiplier=atr_stop_multiplier,
            atr_target_multiplier=atr_target_multiplier
        )
        self.rsi_period = rsi_period
        self.oversold_level = oversold_level
        self.overbought_level = overbought_level
        self.exit_level = exit_level
        self.use_divergence = use_divergence
        self.require_reversal_candle = require_reversal_candle
        self.atr_stop_multiplier = atr_stop_multiplier
        self.atr_target_multiplier = atr_target_multiplier
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on RSI extremes"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # Calculate RSI
        df["RSI"] = self.calculate_rsi(df["Close"], self.rsi_period)
        df["ATR"] = self.calculate_atr(df, 14)
        
        # Track RSI zones
        df["Oversold"] = df["RSI"] < self.oversold_level
        df["Overbought"] = df["RSI"] > self.overbought_level
        
        # RSI recovery/decline
        df["RSI_Rising"] = df["RSI"] > df["RSI"].shift(1)
        df["RSI_Falling"] = df["RSI"] < df["RSI"].shift(1)
        
        # Reversal candle patterns (optional)
        df["Bullish_Candle"] = df["Close"] > df["Open"]
        df["Bearish_Candle"] = df["Close"] < df["Open"]
        
        # Hammer/Doji patterns for reversal confirmation
        body_size = abs(df["Close"] - df["Open"])
        total_range = df["High"] - df["Low"]
        df["Small_Body"] = body_size < (total_range * 0.3)
        df["Lower_Wick"] = df[["Open", "Close"]].min(axis=1) - df["Low"]
        df["Upper_Wick"] = df["High"] - df[["Open", "Close"]].max(axis=1)
        
        # Potential reversal patterns
        df["Bullish_Reversal"] = (df["Lower_Wick"] > body_size * 2) | df["Bullish_Candle"]
        df["Bearish_Reversal"] = (df["Upper_Wick"] > body_size * 2) | df["Bearish_Candle"]
        
        # Initialize signals
        df["Signal"] = 0
        
        # Buy conditions: RSI was oversold, now rising
        oversold_recovery = (
            df["Oversold"].shift(1) &  # Was oversold
            df["RSI_Rising"] &  # RSI turning up
            (df["RSI"] > df["RSI"].shift(1))  # Momentum confirmation
        )
        
        # Sell conditions: RSI was overbought, now falling
        overbought_decline = (
            df["Overbought"].shift(1) &  # Was overbought
            df["RSI_Falling"] &  # RSI turning down
            (df["RSI"] < df["RSI"].shift(1))  # Momentum confirmation
        )
        
        if self.require_reversal_candle:
            oversold_recovery = oversold_recovery & df["Bullish_Reversal"]
            overbought_decline = overbought_decline & df["Bearish_Reversal"]
        
        df.loc[oversold_recovery, "Signal"] = 1
        df.loc[overbought_decline, "Signal"] = -1
        
        # Stop loss and take profit
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        df.loc[df["Signal"] == 1, "StopLoss"] = df["Low"] - (df["ATR"] * self.atr_stop_multiplier)
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["Close"] + (df["ATR"] * self.atr_target_multiplier)
        
        df.loc[df["Signal"] == -1, "StopLoss"] = df["High"] + (df["ATR"] * self.atr_stop_multiplier)
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["Close"] - (df["ATR"] * self.atr_target_multiplier)
        
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        return df


class BollingerBandStrategy(BaseStrategy):
    """
    Bollinger Band Mean Reversion Strategy
    
    Buy when price touches lower band and shows reversal
    Sell when price touches upper band and shows reversal
    
    Uses band width and RSI for confirmation.
    """
    
    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: int = 30,
        rsi_overbought: int = 70,
        require_band_touch: bool = True,
        min_band_width: float = 0.01,
        use_squeeze_filter: bool = True
    ):
        super().__init__(
            name="BollingerBand_MeanReversion",
            bb_period=bb_period,
            bb_std=bb_std,
            rsi_period=rsi_period,
            rsi_oversold=rsi_oversold,
            rsi_overbought=rsi_overbought,
            require_band_touch=require_band_touch,
            min_band_width=min_band_width,
            use_squeeze_filter=use_squeeze_filter
        )
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.require_band_touch = require_band_touch
        self.min_band_width = min_band_width
        self.use_squeeze_filter = use_squeeze_filter
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on Bollinger Bands"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # Calculate Bollinger Bands
        bb_upper, bb_middle, bb_lower = self.calculate_bollinger_bands(
            df["Close"], self.bb_period, self.bb_std
        )
        
        df["BB_Upper"] = bb_upper
        df["BB_Middle"] = bb_middle
        df["BB_Lower"] = bb_lower
        
        # Band width for squeeze detection
        df["BB_Width"] = (df["BB_Upper"] - df["BB_Lower"]) / df["BB_Middle"]
        df["BB_Width_SMA"] = df["BB_Width"].rolling(window=50).mean()
        
        # Calculate RSI
        df["RSI"] = self.calculate_rsi(df["Close"], self.rsi_period)
        df["ATR"] = self.calculate_atr(df, 14)
        
        # Band positions
        df["Above_Upper"] = df["Close"] > df["BB_Upper"]
        df["Below_Lower"] = df["Close"] < df["BB_Lower"]
        df["Touch_Upper"] = df["High"] >= df["BB_Upper"]
        df["Touch_Lower"] = df["Low"] <= df["BB_Lower"]
        
        # %B indicator (position within bands)
        df["Percent_B"] = (df["Close"] - df["BB_Lower"]) / (df["BB_Upper"] - df["BB_Lower"])
        
        # Initialize signals
        df["Signal"] = 0
        
        # Buy conditions: price at/below lower band with RSI oversold
        buy_condition = (
            (df["Touch_Lower"] | df["Below_Lower"]) &
            (df["RSI"] < self.rsi_oversold + 10) &
            (df["Close"] > df["Open"])  # Bullish candle
        )
        
        # Sell conditions: price at/above upper band with RSI overbought
        sell_condition = (
            (df["Touch_Upper"] | df["Above_Upper"]) &
            (df["RSI"] > self.rsi_overbought - 10) &
            (df["Close"] < df["Open"])  # Bearish candle
        )
        
        # Filter out squeeze conditions if enabled (low volatility = avoid)
        if self.use_squeeze_filter:
            in_squeeze = df["BB_Width"] < df["BB_Width_SMA"] * 0.8
            buy_condition = buy_condition & ~in_squeeze
            sell_condition = sell_condition & ~in_squeeze
        
        # Require minimum band width
        wide_enough = df["BB_Width"] > self.min_band_width
        buy_condition = buy_condition & wide_enough
        sell_condition = sell_condition & wide_enough
        
        df.loc[buy_condition, "Signal"] = 1
        df.loc[sell_condition, "Signal"] = -1
        
        # Stop loss at opposite band, take profit at middle band
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        # For long entries: stop below lower band, target middle band
        df.loc[df["Signal"] == 1, "StopLoss"] = df["BB_Lower"] - (df["ATR"] * 0.5)
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["BB_Middle"]
        
        # For short entries: stop above upper band, target middle band
        df.loc[df["Signal"] == -1, "StopLoss"] = df["BB_Upper"] + (df["ATR"] * 0.5)
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["BB_Middle"]
        
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        return df


class StatisticalArbitrageStrategy(BaseStrategy):
    """
    Statistical Arbitrage / Z-Score Mean Reversion
    
    Uses z-score of price relative to moving average.
    Enters when z-score reaches extreme levels.
    """
    
    def __init__(
        self,
        lookback_period: int = 20,
        entry_z_score: float = 2.0,
        exit_z_score: float = 0.5,
        max_holding_period: int = 20
    ):
        super().__init__(
            name="StatArb_ZScore",
            lookback_period=lookback_period,
            entry_z_score=entry_z_score,
            exit_z_score=exit_z_score,
            max_holding_period=max_holding_period
        )
        self.lookback_period = lookback_period
        self.entry_z_score = entry_z_score
        self.exit_z_score = exit_z_score
        self.max_holding_period = max_holding_period
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on z-score extremes"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # Calculate z-score
        df["SMA"] = df["Close"].rolling(window=self.lookback_period).mean()
        df["STD"] = df["Close"].rolling(window=self.lookback_period).std()
        df["ZScore"] = (df["Close"] - df["SMA"]) / df["STD"]
        df["ATR"] = self.calculate_atr(df, 14)
        
        # Initialize signals
        df["Signal"] = 0
        
        # Entry signals
        # Buy when z-score is extremely negative (price below mean)
        df.loc[df["ZScore"] < -self.entry_z_score, "Signal"] = 1
        
        # Sell when z-score is extremely positive (price above mean)
        df.loc[df["ZScore"] > self.entry_z_score, "Signal"] = -1
        
        # Exit when z-score returns to normal
        # This is handled by position tracking in backtest engine
        
        # Stop loss and take profit based on mean reversion expectation
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        # For long: stop at further extreme, target mean
        df.loc[df["Signal"] == 1, "StopLoss"] = df["SMA"] - (df["STD"] * (self.entry_z_score + 1))
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["SMA"]
        
        # For short: stop at further extreme, target mean
        df.loc[df["Signal"] == -1, "StopLoss"] = df["SMA"] + (df["STD"] * (self.entry_z_score + 1))
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["SMA"]
        
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        return df
