import pandas as pd
from backtesting import Strategy
from utils import ema200, bol_h, bol_l, rsi
from position_manager import calculate_qty
from config import RISK_FRACTION

def adjust_size_for_backtest(size):
    return size if size < 1 else max(1, int(size))

class BBRSI_EMA_Strategy(Strategy):
    bol_period = 40
    bol_dev = 2
    rsi_period = 14

    def init(self):
        self.bol_h = self.I(bol_h, self.data.Close, self.bol_period, self.bol_dev)
        self.bol_l = self.I(bol_l, self.data.Close, self.bol_period, self.bol_dev)
        self.rsi = self.I(rsi, self.data.Close, self.rsi_period)
        self.ema200 = self.I(ema200, self.data.Close)

    def next(self):
        price = float(self.data.Close[-1])
        size = adjust_size_for_backtest(calculate_qty(price, self.equity, RISK_FRACTION))
        if price > self.ema200[-1]:
            if self.data.Close[-3] > self.bol_l[-3] and self.data.Close[-2] < self.bol_l[-2] and self.rsi[-1] < 30:
                if not self.position:
                    self.buy(size=size)
                elif self.position.is_short:
                    self.position.close()
                    self.buy(size=size)
        elif price < self.ema200[-1]:
            if self.data.Close[-3] < self.bol_h[-3] and self.data.Close[-2] > self.bol_h[-2] and self.rsi[-1] > 70:
                if not self.position:
                    self.sell(size=size)
                elif self.position.is_long:
                    self.position.close()
                    self.sell(size=size)

class Breakout_Strategy(Strategy):
    period = 20

    def init(self):
        self.highest = self.I(lambda x: pd.Series(x).rolling(self.period).max(), self.data.High)
        self.lowest = self.I(lambda x: pd.Series(x).rolling(self.period).min(), self.data.Low)

    def next(self):
        price = float(self.data.Close[-1])
        size = adjust_size_for_backtest(calculate_qty(price, self.equity, RISK_FRACTION))
        if price > self.highest[-2]:
            if not self.position or self.position.is_short:
                if self.position:
                    self.position.close()
                self.buy(size=size)
        elif price < self.lowest[-2]:
            if not self.position or self.position.is_long:
                if self.position:
                    self.position.close()
                self.sell(size=size)
