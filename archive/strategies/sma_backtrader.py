# strategies/sma_backtrader.py
import backtrader as bt

class SmaCross(bt.Strategy):
    params = (("pfast", 20), ("pslow", 50), ("risk_fraction", 0.1),)

    def __init__(self):
        sma_fast = bt.ind.SMA(self.data.close, period=self.p.pfast)
        sma_slow = bt.ind.SMA(self.data.close, period=self.p.pslow)
        self.crossover = bt.ind.CrossOver(sma_fast, sma_slow)

    def next(self):
        if not self.position:
            if self.crossover > 0:
                # compute position size: risk_fraction of cash
                cash = self.broker.getcash()
                price = self.data.close[0]
                size = int((cash * self.p.risk_fraction) / price)
                if size > 0:
                    self.buy(size=size)
        elif self.crossover < 0:
            # exit
            self.close()
