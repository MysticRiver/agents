"""Tests for trading strategies"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.strategies.momentum import MACrossoverStrategy, BreakoutStrategy
from src.strategies.mean_reversion import RSIMeanReversionStrategy, BollingerBandStrategy
from src.strategies.volatility import ATRBreakoutStrategy
from src.strategies.time_based import OpeningRangeBreakoutStrategy


@pytest.fixture
def sample_data():
    """Generate sample OHLCV data for testing"""
    np.random.seed(42)
    n = 500
    
    dates = pd.date_range(start='2024-01-01 09:30', periods=n, freq='5min')
    
    base_price = 18000
    returns = np.random.normal(0.0001, 0.002, n)
    prices = base_price * np.exp(np.cumsum(returns))
    
    df = pd.DataFrame({
        'Open': prices * (1 + np.random.normal(0, 0.001, n)),
        'High': prices * (1 + np.abs(np.random.normal(0, 0.002, n))),
        'Low': prices * (1 - np.abs(np.random.normal(0, 0.002, n))),
        'Close': prices,
        'Volume': np.random.randint(1000, 10000, n)
    }, index=dates)
    
    df['High'] = df[['Open', 'High', 'Close']].max(axis=1)
    df['Low'] = df[['Open', 'Low', 'Close']].min(axis=1)
    
    return df


class TestMACrossoverStrategy:
    """Tests for MA Crossover Strategy"""
    
    def test_generate_signals_returns_dataframe(self, sample_data):
        strategy = MACrossoverStrategy(fast_period=5, slow_period=10)
        result = strategy.generate_signals(sample_data)
        
        assert isinstance(result, pd.DataFrame)
        assert 'Signal' in result.columns
        assert len(result) == len(sample_data)
    
    def test_signals_are_valid_values(self, sample_data):
        strategy = MACrossoverStrategy()
        result = strategy.generate_signals(sample_data)
        
        valid_signals = [-1, 0, 1]
        assert all(s in valid_signals for s in result['Signal'].unique())
    
    def test_ema_columns_added(self, sample_data):
        strategy = MACrossoverStrategy(fast_period=5, slow_period=10)
        result = strategy.generate_signals(sample_data)
        
        assert 'EMA_Fast' in result.columns
        assert 'EMA_Slow' in result.columns


class TestRSIMeanReversionStrategy:
    """Tests for RSI Mean Reversion Strategy"""
    
    def test_generate_signals_returns_dataframe(self, sample_data):
        strategy = RSIMeanReversionStrategy(rsi_period=14)
        result = strategy.generate_signals(sample_data)
        
        assert isinstance(result, pd.DataFrame)
        assert 'Signal' in result.columns
        assert 'RSI' in result.columns
    
    def test_rsi_range(self, sample_data):
        strategy = RSIMeanReversionStrategy()
        result = strategy.generate_signals(sample_data)
        
        rsi_values = result['RSI'].dropna()
        assert all(0 <= v <= 100 for v in rsi_values)


class TestBollingerBandStrategy:
    """Tests for Bollinger Band Strategy"""
    
    def test_bands_calculated(self, sample_data):
        strategy = BollingerBandStrategy(bb_period=20)
        result = strategy.generate_signals(sample_data)
        
        assert 'BB_Upper' in result.columns
        assert 'BB_Middle' in result.columns
        assert 'BB_Lower' in result.columns
    
    def test_upper_above_lower(self, sample_data):
        strategy = BollingerBandStrategy()
        result = strategy.generate_signals(sample_data)
        
        valid = result.dropna()
        assert all(valid['BB_Upper'] > valid['BB_Lower'])


class TestATRBreakoutStrategy:
    """Tests for ATR Breakout Strategy"""
    
    def test_atr_calculated(self, sample_data):
        strategy = ATRBreakoutStrategy(atr_period=14)
        result = strategy.generate_signals(sample_data)
        
        assert 'ATR' in result.columns
        assert all(result['ATR'].dropna() >= 0)


class TestOpeningRangeBreakoutStrategy:
    """Tests for Opening Range Breakout Strategy"""
    
    def test_or_levels_calculated(self, sample_data):
        strategy = OpeningRangeBreakoutStrategy(opening_range_minutes=30)
        result = strategy.generate_signals(sample_data)
        
        assert 'OR_High' in result.columns
        assert 'OR_Low' in result.columns


class TestStrategyParameters:
    """Test strategy parameter handling"""
    
    def test_parameters_stored(self):
        strategy = MACrossoverStrategy(fast_period=5, slow_period=20)
        params = strategy.parameters
        
        assert params['fast_period'] == 5
        assert params['slow_period'] == 20
    
    def test_default_parameters(self):
        strategy = MACrossoverStrategy()
        params = strategy.parameters
        
        assert 'fast_period' in params
        assert 'slow_period' in params
