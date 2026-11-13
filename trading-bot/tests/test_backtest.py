"""Tests for backtesting engine"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from src.backtest.engine import BacktestEngine, BacktestResult
from src.backtest.metrics import calculate_metrics
from src.strategies.momentum import MACrossoverStrategy


@pytest.fixture
def sample_data():
    """Generate sample data for backtesting"""
    np.random.seed(42)
    n = 1000
    
    dates = pd.date_range(start='2024-01-01 09:30', periods=n, freq='5min')
    
    base_price = 18000
    returns = np.random.normal(0.0002, 0.002, n)
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


@pytest.fixture
def backtest_engine():
    """Create backtest engine instance"""
    return BacktestEngine(
        initial_capital=10000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=3
    )


class TestBacktestEngine:
    """Tests for BacktestEngine"""
    
    def test_run_returns_result(self, sample_data, backtest_engine):
        strategy = MACrossoverStrategy(fast_period=5, slow_period=10)
        result = backtest_engine.run(sample_data, strategy)
        
        assert isinstance(result, BacktestResult)
    
    def test_result_contains_metrics(self, sample_data, backtest_engine):
        strategy = MACrossoverStrategy()
        result = backtest_engine.run(sample_data, strategy)
        
        assert result.metrics is not None
        assert hasattr(result.metrics, 'sharpe_ratio')
        assert hasattr(result.metrics, 'max_drawdown_pct')
    
    def test_result_contains_trades(self, sample_data, backtest_engine):
        strategy = MACrossoverStrategy()
        result = backtest_engine.run(sample_data, strategy)
        
        assert isinstance(result.trades, list)
    
    def test_equity_curve_generated(self, sample_data, backtest_engine):
        strategy = MACrossoverStrategy()
        result = backtest_engine.run(sample_data, strategy)
        
        assert isinstance(result.equity_curve, pd.Series)
        assert len(result.equity_curve) > 0
    
    def test_initial_capital_respected(self, sample_data):
        initial = 25000.0
        engine = BacktestEngine(initial_capital=initial)
        strategy = MACrossoverStrategy()
        result = engine.run(sample_data, strategy)
        
        assert result.initial_capital == initial
        assert result.equity_curve.iloc[0] == initial
    
    def test_commission_applied(self, sample_data):
        engine_with_commission = BacktestEngine(commission_per_contract=5.0)
        engine_no_commission = BacktestEngine(commission_per_contract=0.0)
        
        strategy = MACrossoverStrategy()
        
        result_with = engine_with_commission.run(sample_data, strategy)
        result_without = engine_no_commission.run(sample_data, strategy)
        
        if len(result_with.trades) > 0 and len(result_without.trades) > 0:
            total_commission = sum(t.commission for t in result_with.trades)
            assert total_commission > 0


class TestMetricsCalculation:
    """Tests for metrics calculation"""
    
    def test_sharpe_ratio_calculation(self):
        equity = pd.Series([10000, 10100, 10050, 10200, 10150, 10300])
        equity.index = pd.date_range('2024-01-01', periods=6, freq='D')
        
        metrics = calculate_metrics(equity, [], 10000)
        
        assert isinstance(metrics.sharpe_ratio, float)
    
    def test_max_drawdown_calculation(self):
        equity = pd.Series([10000, 10500, 10200, 9800, 10100, 10300])
        equity.index = pd.date_range('2024-01-01', periods=6, freq='D')
        
        metrics = calculate_metrics(equity, [], 10000)
        
        assert metrics.max_drawdown_pct < 0  # Drawdown is negative
        assert metrics.max_drawdown_pct >= -100
    
    def test_win_rate_calculation(self, sample_data, backtest_engine):
        strategy = MACrossoverStrategy()
        result = backtest_engine.run(sample_data, strategy)
        
        if result.metrics.total_trades > 0:
            assert 0 <= result.metrics.win_rate <= 100
