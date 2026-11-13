"""Data fetching and handling for MNQ futures"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple
from pathlib import Path
import yfinance as yf
from loguru import logger


class MNQDataFetcher:
    """Fetch MNQ/NQ futures data from various sources"""
    
    TICK_SIZE = 0.25
    TICK_VALUE = 0.50  # $0.50 per tick for MNQ
    POINT_VALUE = 2.00  # $2.00 per point for MNQ (1 point = 4 ticks)
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
    def fetch_nq_data(
        self, 
        start_date: str,
        end_date: Optional[str] = None,
        interval: str = "1m"
    ) -> pd.DataFrame:
        """
        Fetch NQ futures data using yfinance.
        Uses NQ=F (E-mini Nasdaq 100) as proxy for MNQ (same price, smaller contract).
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date (defaults to today)
            interval: Data interval (1m, 5m, 15m, 1h, 1d)
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
            
        logger.info(f"Fetching NQ data from {start_date} to {end_date}, interval={interval}")
        
        ticker = yf.Ticker("NQ=F")
        df = ticker.history(start=start_date, end=end_date, interval=interval)
        
        if df.empty:
            logger.warning("No data returned from yfinance, generating synthetic data")
            df = self._generate_synthetic_data(start_date, end_date, interval)
        
        df = self._clean_data(df)
        return df
    
    def _generate_synthetic_data(
        self, 
        start_date: str, 
        end_date: str, 
        interval: str
    ) -> pd.DataFrame:
        """Generate realistic synthetic MNQ data for backtesting"""
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        
        interval_map = {
            "1m": "1min",
            "5m": "5min", 
            "15m": "15min",
            "1h": "1h",
            "1d": "1D"
        }
        
        freq = interval_map.get(interval, "1min")
        
        date_range = pd.date_range(start=start, end=end, freq=freq)
        
        # Filter to market hours (6:00 PM - 5:00 PM ET next day, Sun-Fri)
        market_hours = []
        for dt in date_range:
            hour = dt.hour
            weekday = dt.weekday()
            
            # Skip Saturday
            if weekday == 5:
                continue
            # Sunday only after 6 PM
            if weekday == 6 and hour < 18:
                continue
            # Friday only before 5 PM
            if weekday == 4 and hour >= 17:
                continue
                
            market_hours.append(dt)
        
        n = len(market_hours)
        if n == 0:
            raise ValueError("No market hours in date range")
            
        # Generate realistic price movement using mean-reverting process
        np.random.seed(42)
        base_price = 18000  # Approximate NQ price
        
        # Mean-reverting Ornstein-Uhlenbeck process for more realistic futures
        theta = 0.1  # Mean reversion speed
        mu = 0.0  # Long-term mean return
        sigma = 0.0015  # Volatility
        
        prices = np.zeros(n)
        prices[0] = base_price
        
        for i in range(1, n):
            # Add both trend and mean reversion components
            trend = np.random.normal(0.00005, sigma)  # Slight upward drift
            reversion = -theta * (np.log(prices[i-1]) - np.log(base_price)) * 0.0001
            shock = np.random.normal(0, sigma)
            
            log_return = trend + reversion + shock
            prices[i] = prices[i-1] * np.exp(log_return)
            
        # Ensure prices stay reasonable
        prices = np.clip(prices, base_price * 0.8, base_price * 1.2)
        
        # Generate OHLC from close prices
        high_noise = np.abs(np.random.normal(0, sigma * 0.5, n))
        low_noise = np.abs(np.random.normal(0, sigma * 0.5, n))
        open_noise = np.random.normal(0, sigma * 0.3, n)
        
        df = pd.DataFrame({
            "Open": prices * (1 + open_noise),
            "High": prices * (1 + high_noise),
            "Low": prices * (1 - low_noise),
            "Close": prices,
            "Volume": np.random.randint(1000, 50000, n)
        }, index=pd.DatetimeIndex(market_hours))
        
        # Ensure High >= Open, Close and Low <= Open, Close
        df["High"] = df[["Open", "High", "Close"]].max(axis=1)
        df["Low"] = df[["Open", "Low", "Close"]].min(axis=1)
        
        # Round to tick size
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = (df[col] / self.TICK_SIZE).round() * self.TICK_SIZE
            
        return df
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and prepare data"""
        df = df.copy()
        
        # Standardize column names
        df.columns = [c.title() for c in df.columns]
        
        # Remove any rows with NaN
        df = df.dropna()
        
        # Ensure proper dtypes
        for col in ["Open", "High", "Low", "Close"]:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        if "Volume" in df.columns:
            df["Volume"] = df["Volume"].astype(int)
            
        # Sort by index
        df = df.sort_index()
        
        return df
    
    def resample_data(self, df: pd.DataFrame, target_interval: str) -> pd.DataFrame:
        """Resample data to different timeframe"""
        interval_map = {
            "1m": "1min",
            "5m": "5min",
            "15m": "15min",
            "1h": "1h",
            "1d": "1D"
        }
        
        freq = interval_map.get(target_interval, target_interval)
        
        resampled = df.resample(freq).agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum"
        }).dropna()
        
        return resampled
    
    def save_data(self, df: pd.DataFrame, filename: str) -> Path:
        """Save data to CSV"""
        filepath = self.data_dir / filename
        df.to_csv(filepath)
        logger.info(f"Saved data to {filepath}")
        return filepath
    
    def load_data(self, filename: str) -> pd.DataFrame:
        """Load data from CSV"""
        filepath = self.data_dir / filename
        df = pd.read_csv(filepath, index_col=0, parse_dates=True)
        return df


class DataHandler:
    """Main data handler for the trading system"""
    
    def __init__(self, data_dir: str = "data"):
        self.fetcher = MNQDataFetcher(data_dir)
        self._data_cache = {}
        
    def get_data(
        self,
        start_date: str,
        end_date: Optional[str] = None,
        interval: str = "1m",
        use_cache: bool = True
    ) -> pd.DataFrame:
        """Get historical data with caching"""
        cache_key = f"{start_date}_{end_date}_{interval}"
        
        if use_cache and cache_key in self._data_cache:
            return self._data_cache[cache_key].copy()
        
        df = self.fetcher.fetch_nq_data(start_date, end_date, interval)
        
        if use_cache:
            self._data_cache[cache_key] = df.copy()
            
        return df
    
    def get_multi_timeframe_data(
        self,
        start_date: str,
        end_date: Optional[str] = None,
        intervals: list = ["1m", "5m"]
    ) -> dict:
        """Get data for multiple timeframes"""
        result = {}
        
        # Fetch smallest interval first
        base_interval = min(intervals, key=lambda x: self._interval_to_minutes(x))
        base_data = self.get_data(start_date, end_date, base_interval)
        result[base_interval] = base_data
        
        # Resample for larger intervals
        for interval in intervals:
            if interval != base_interval:
                result[interval] = self.fetcher.resample_data(base_data, interval)
                
        return result
    
    @staticmethod
    def _interval_to_minutes(interval: str) -> int:
        """Convert interval string to minutes"""
        mapping = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "1d": 1440}
        return mapping.get(interval, 1)
    
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add common technical indicators"""
        df = df.copy()
        
        # Moving Averages
        df["SMA_10"] = df["Close"].rolling(10).mean()
        df["SMA_20"] = df["Close"].rolling(20).mean()
        df["SMA_50"] = df["Close"].rolling(50).mean()
        df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
        df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
        
        # RSI
        df["RSI"] = self._calculate_rsi(df["Close"], 14)
        
        # MACD
        exp1 = df["Close"].ewm(span=12, adjust=False).mean()
        exp2 = df["Close"].ewm(span=26, adjust=False).mean()
        df["MACD"] = exp1 - exp2
        df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
        df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]
        
        # Bollinger Bands
        df["BB_Mid"] = df["Close"].rolling(20).mean()
        bb_std = df["Close"].rolling(20).std()
        df["BB_Upper"] = df["BB_Mid"] + (bb_std * 2)
        df["BB_Lower"] = df["BB_Mid"] - (bb_std * 2)
        df["BB_Width"] = (df["BB_Upper"] - df["BB_Lower"]) / df["BB_Mid"]
        
        # ATR
        df["ATR"] = self._calculate_atr(df, 14)
        
        # Stochastic
        df["Stoch_K"], df["Stoch_D"] = self._calculate_stochastic(df, 14, 3)
        
        # Volume indicators
        df["Volume_SMA"] = df["Volume"].rolling(20).mean()
        df["Volume_Ratio"] = df["Volume"] / df["Volume_SMA"]
        
        # Price momentum
        df["ROC"] = df["Close"].pct_change(10) * 100
        
        # Volatility
        df["Volatility"] = df["Close"].pct_change().rolling(20).std() * np.sqrt(252 * 390)
        
        return df
    
    @staticmethod
    def _calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def _calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr
    
    @staticmethod
    def _calculate_stochastic(
        df: pd.DataFrame, 
        k_period: int = 14, 
        d_period: int = 3
    ) -> Tuple[pd.Series, pd.Series]:
        """Calculate Stochastic oscillator"""
        low_min = df["Low"].rolling(window=k_period).min()
        high_max = df["High"].rolling(window=k_period).max()
        
        stoch_k = 100 * (df["Close"] - low_min) / (high_max - low_min)
        stoch_d = stoch_k.rolling(window=d_period).mean()
        
        return stoch_k, stoch_d
