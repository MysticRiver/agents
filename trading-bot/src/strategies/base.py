"""Base strategy class"""
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from loguru import logger


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.
    
    All strategies must implement:
    - generate_signals(): Return DataFrame with Signal column (1=buy, -1=sell, 0=hold)
    """
    
    def __init__(self, name: str = "BaseStrategy", **kwargs):
        self.name = name
        self._parameters = kwargs
        
    @property
    def parameters(self) -> Dict[str, Any]:
        """Return strategy parameters"""
        return self._parameters.copy()
    
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate trading signals based on price data.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added Signal column (1=buy, -1=sell, 0=hold)
        """
        pass
    
    def _add_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators needed by the strategy"""
        return data.copy()
    
    def _validate_data(self, data: pd.DataFrame) -> bool:
        """Validate input data has required columns"""
        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = [col for col in required if col not in data.columns]
        if missing:
            logger.error(f"Missing required columns: {missing}")
            return False
        return True
    
    @staticmethod
    def calculate_sma(series: pd.Series, period: int) -> pd.Series:
        """Calculate Simple Moving Average"""
        return series.rolling(window=period).mean()
    
    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return series.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high = data["High"]
        low = data["Low"]
        close = data["Close"]
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    @staticmethod
    def calculate_bollinger_bands(
        series: pd.Series, 
        period: int = 20, 
        std_dev: float = 2.0
    ) -> tuple:
        """Calculate Bollinger Bands"""
        middle = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower
    
    @staticmethod
    def calculate_stochastic(
        data: pd.DataFrame,
        k_period: int = 14,
        d_period: int = 3
    ) -> tuple:
        """Calculate Stochastic Oscillator"""
        low_min = data["Low"].rolling(window=k_period).min()
        high_max = data["High"].rolling(window=k_period).max()
        
        k = 100 * (data["Close"] - low_min) / (high_max - low_min)
        d = k.rolling(window=d_period).mean()
        return k, d
    
    @staticmethod
    def calculate_macd(
        series: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> tuple:
        """Calculate MACD"""
        exp1 = series.ewm(span=fast, adjust=False).mean()
        exp2 = series.ewm(span=slow, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
