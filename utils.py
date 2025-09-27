import pandas as pd
import numpy as np
import ta
from decimal import Decimal, ROUND_DOWN

def ema200(arr):
    s = pd.Series(arr)
    return s.ewm(span=200, adjust=False).mean().to_numpy()

def bol_h(arr, period=40, dev=2):
    s = pd.Series(arr) if not isinstance(arr, pd.Series) else arr
    bb = ta.volatility.BollingerBands(s, window=period, window_dev=dev)
    return bb.bollinger_hband().to_numpy()

def bol_l(arr, period=40, dev=2):
    s = pd.Series(arr) if not isinstance(arr, pd.Series) else arr
    bb = ta.volatility.BollingerBands(s, window=period, window_dev=dev)
    return bb.bollinger_lband().to_numpy()

def rsi(arr, period=14):
    s = pd.Series(arr) if not isinstance(arr, pd.Series) else arr
    return ta.momentum.RSIIndicator(s, window=period).rsi().to_numpy()

def atr(arr_high, arr_low, arr_close, period=14):
    df = pd.DataFrame({"high": arr_high, "low": arr_low, "close": arr_close})
    return ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=period).average_true_range().to_numpy()

def _quantize_to_step(value: float, step: float) -> float:
    d_val = Decimal(str(value))
    d_step = Decimal(str(step))
    steps = (d_val / d_step).to_integral_value(rounding=ROUND_DOWN)
    return float(steps * d_step)

def clean_klines(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    df[["Open", "High", "Low", "Close", "Volume"]] = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    df = df[(df["Open"] > 0) & (df["High"] > 0) & (df["Low"] > 0) & (df["Close"] > 0)]
    return df
