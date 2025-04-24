import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Tuple, Optional, Union, Literal
from enum import Enum

class TrendDirection(Enum):
    UPTREND = "上升趋势"
    DOWNTREND = "下降趋势"
    SIDEWAYS = "盘整"
    
class TimeFrame(Enum):
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    HOUR_8 = "8h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"

class SignalType(Enum):
    BUY = "买入"
    SELL = "卖出"
    HOLD = "持有"

class TrendAnalyzer:
    """多指标组合趋势分析器"""
    
    def __init__(self):
        self.logger = logging.getLogger("TrendAnalyzer")
        self.logger.info("趋势分析器初始化")
    
    @staticmethod
    def calculate_ema(data: np.ndarray, period: int) -> np.ndarray:
        """计算EMA指标"""
        ema = np.zeros_like(data)
        alpha = 2 / (period + 1)
        
        # 初始化第一个EMA值为简单平均值
        ema[0] = np.mean(data[:period])
        
        # 计算其余的EMA值
        for i in range(1, len(data)):
            ema[i] = data[i] * alpha + ema[i-1] * (1 - alpha)
            
        return ema
    
    @staticmethod
    def calculate_macd(data: np.ndarray, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """计算MACD指标"""
        ema_fast = TrendAnalyzer.calculate_ema(data, fast_period)
        ema_slow = TrendAnalyzer.calculate_ema(data, slow_period)
        
        # MACD线 = 快速EMA - 慢速EMA
        macd_line = ema_fast - ema_slow
        
        # 信号线 = MACD的EMA
        signal_line = TrendAnalyzer.calculate_ema(macd_line, signal_period)
        
        # MACD柱状图 = MACD线 - 信号线
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def calculate_rsi(data: np.ndarray, period: int = 14) -> np.ndarray:
        """计算RSI指标"""
        deltas = np.diff(data)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum()/period
        down = -seed[seed < 0].sum()/period
        
        if down != 0:
            rs = up/down
        else:
            rs = 1
            
        rsi = np.zeros_like(data)
        rsi[0] = 100. - 100./(1. + rs)
        
        for i in range(1, len(data)):
            delta = deltas[i-1]
            
            if delta > 0:
                upval = delta
                downval = 0
            else:
                upval = 0
                downval = -delta
                
            up = (up * (period - 1) + upval) / period
            down = (down * (period - 1) + downval) / period
            
            if down != 0:
                rs = up/down
            else:
                rs = 1
                
            rsi[i] = 100. - 100./(1. + rs)
            
        return rsi
    
    @staticmethod
    def calculate_kdj(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 9, m1: int = 3, m2: int = 3) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """计算KDJ指标"""
        rsv = np.zeros_like(close)
        k = np.zeros_like(close)
        d = np.zeros_like(close)
        j = np.zeros_like(close)
        
        for i in range(n-1, len(close)):
            period_low = np.min(low[i-n+1:i+1])
            period_high = np.max(high[i-n+1:i+1])
            
            if period_high != period_low:
                rsv[i] = (close[i] - period_low) / (period_high - period_low) * 100
            else:
                rsv[i] = 50
            
            if i == n-1:
                k[i] = rsv[i]
                d[i] = k[i]
            else:
                k[i] = (m1 * k[i-1] + rsv[i]) / (m1 + 1)
                d[i] = (m2 * d[i-1] + k[i]) / (m2 + 1)
            
            j[i] = 3 * k[i] - 2 * d[i]
        
        return k, d, j
    
    @staticmethod
    def calculate_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """计算ATR指标"""
        tr = np.zeros(len(high))
        tr[0] = high[0] - low[0]  # 第一个TR值设为当天的高低差
        
        for i in range(1, len(tr)):
            tr[i] = max(
                high[i] - low[i],  # 当前bar的范围
                abs(high[i] - close[i-1]),  # 当前最高与前一收盘价的差
                abs(low[i] - close[i-1])  # 当前最低与前一收盘价的差
            )
        
        # 计算ATR
        atr = np.zeros_like(tr)
        atr[period-1] = np.mean(tr[:period])  # 第一个ATR值使用简单平均
        
        # 使用加权移动平均计算后续ATR
        for i in range(period, len(atr)):
            atr[i] = (atr[i-1] * (period-1) + tr[i]) / period
            
        return atr

class TrendTradingSystem:
    """趋势交易系统"""
    
    def __init__(self):
        self.analyzer = TrendAnalyzer()
        self.logger = logging.getLogger("TrendTradingSystem")
        self.logger.info("趋势交易系统初始化")
        
    def analyze_ema_trend(self, 
                         data: pd.DataFrame, 
                         short_period: int = 30, 
                         mid_period: int = 60, 
                         long_period: int = 120) -> TrendDirection:
        """分析EMA均线趋势"""
        close_prices = data['close'].values
        
        # 计算三条EMA均线
        ema_short = self.analyzer.calculate_ema(close_prices, short_period)
        ema_mid = self.analyzer.calculate_ema(close_prices, mid_period)
        ema_long = self.analyzer.calculate_ema(close_prices, long_period)
        
        # 获取最新的均线值
        latest_ema_short = ema_short[-1]
        latest_ema_mid = ema_mid[-1]
        latest_ema_long = ema_long[-1]
        
        # 判断均线排列
        if latest_ema_short > latest_ema_mid > latest_ema_long:
            return TrendDirection.UPTREND
        elif latest_ema_short < latest_ema_mid < latest_ema_long:
            return TrendDirection.DOWNTREND
        else:
            return TrendDirection.SIDEWAYS
    
    def analyze_macd_trend(self, data: pd.DataFrame) -> TrendDirection:
        """分析MACD趋势"""
        close_prices = data['close'].values
        
        # 计算MACD指标
        macd_line, signal_line, histogram = self.analyzer.calculate_macd(close_prices)
        
        # 获取最近的MACD值
        recent_macd = macd_line[-3:]
        recent_histogram = histogram[-3:]
        
        # 判断MACD趋势
        if macd_line[-1] > 0 and histogram[-1] > 0:
            # MACD和柱状图都为正，强烈上升趋势
            return TrendDirection.UPTREND
        elif macd_line[-1] < 0 and histogram[-1] < 0:
            # MACD和柱状图都为负，强烈下降趋势
            return TrendDirection.DOWNTREND
        elif histogram[-1] > histogram[-2] > histogram[-3]:
            # 柱状图连续增长，可能是趋势转为上升
            return TrendDirection.UPTREND
        elif histogram[-1] < histogram[-2] < histogram[-3]:
            # 柱状图连续减少，可能是趋势转为下降
            return TrendDirection.DOWNTREND
        else:
            # 其他情况视为盘整
            return TrendDirection.SIDEWAYS
    
    def analyze_rsi_trend(self, data: pd.DataFrame, period: int = 14, 
                          overbought: int = 70, oversold: int = 30) -> TrendDirection:
        """分析RSI趋势"""
        close_prices = data['close'].values
        
        # 计算RSI
        rsi = self.analyzer.calculate_rsi(close_prices, period)
        latest_rsi = rsi[-1]
        
        # 判断RSI趋势
        if latest_rsi > overbought:
            return TrendDirection.UPTREND
        elif latest_rsi < oversold:
            return TrendDirection.DOWNTREND
        else:
            return TrendDirection.SIDEWAYS
    
    def analyze_kdj_trend(self, data: pd.DataFrame) -> TrendDirection:
        """分析KDJ趋势"""
        high_prices = data['high'].values
        low_prices = data['low'].values
        close_prices = data['close'].values
        
        # 计算KDJ
        k, d, j = self.analyzer.calculate_kdj(high_prices, low_prices, close_prices)
        
        # 获取最新值
        latest_k = k[-1]
        latest_d = d[-1]
        latest_j = j[-1]
        
        # 判断KDJ趋势
        if latest_k > latest_d and latest_j > 0:
            return TrendDirection.UPTREND
        elif latest_k < latest_d and latest_j < 100:
            return TrendDirection.DOWNTREND
        else:
            return TrendDirection.SIDEWAYS
    
    def calculate_risk_position(self, data: pd.DataFrame, risk_per_trade: float = 0.02, 
                               atr_multiplier: float = 2.0) -> float:
        """计算基于ATR的风险仓位"""
        high_prices = data['high'].values
        low_prices = data['low'].values
        close_prices = data['close'].values
        
        # 计算ATR
        atr = self.analyzer.calculate_atr(high_prices, low_prices, close_prices)
        latest_atr = atr[-1]
        latest_close = close_prices[-1]
        
        # 计算止损点
        stop_loss_distance = latest_atr * atr_multiplier
        
        # 根据风险计算仓位
        position_size = risk_per_trade / (stop_loss_distance / latest_close)
        
        return position_size
    
    def generate_signal(self, data: pd.DataFrame) -> SignalType:
        """生成交易信号"""
        # 分析各个指标的趋势
        ema_trend = self.analyze_ema_trend(data)
        macd_trend = self.analyze_macd_trend(data)
        rsi_trend = self.analyze_rsi_trend(data)
        kdj_trend = self.analyze_kdj_trend(data)
        
        # 记录各个指标的判断结果
        self.logger.info(f"EMA趋势: {ema_trend.value}")
        self.logger.info(f"MACD趋势: {macd_trend.value}")
        self.logger.info(f"RSI趋势: {rsi_trend.value}")
        self.logger.info(f"KDJ趋势: {kdj_trend.value}")
        
        # 综合判断交易信号
        uptrend_count = sum(1 for trend in [ema_trend, macd_trend, rsi_trend, kdj_trend] 
                          if trend == TrendDirection.UPTREND)
        downtrend_count = sum(1 for trend in [ema_trend, macd_trend, rsi_trend, kdj_trend] 
                            if trend == TrendDirection.DOWNTREND)
        
        # 至少有3个指标显示同一方向的趋势才生成信号
        if uptrend_count >= 3:
            return SignalType.BUY
        elif downtrend_count >= 3:
            return SignalType.SELL
        else:
            return SignalType.HOLD
    
    def execute_strategy(self, data: pd.DataFrame) -> Dict:
        """执行趋势交易策略"""
        signal = self.generate_signal(data)
        position_size = 0
        stop_loss = 0
        take_profit = 0
        
        if signal == SignalType.BUY or signal == SignalType.SELL:
            # 计算仓位大小和风险控制
            risk_position = self.calculate_risk_position(data)
            
            # 计算止损和止盈
            high_prices = data['high'].values
            low_prices = data['low'].values
            close_prices = data['close'].values
            latest_close = close_prices[-1]
            
            atr = self.analyzer.calculate_atr(high_prices, low_prices, close_prices)
            latest_atr = atr[-1]
            
            if signal == SignalType.BUY:
                stop_loss = latest_close - (latest_atr * 2)
                take_profit = latest_close + (latest_atr * 3)  # 风险收益比1:1.5
                position_size = risk_position
            else:  # SELL
                stop_loss = latest_close + (latest_atr * 2)
                take_profit = latest_close - (latest_atr * 3)  # 风险收益比1:1.5
                position_size = risk_position
        
        result = {
            "signal": signal.value,
            "position_size": position_size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "current_price": data['close'].values[-1]
        }
        
        self.logger.info(f"交易信号: {result}")
        
        return result

class MultiTimeframeTrendSystem:
    """多周期趋势交易系统"""
    
    def __init__(self):
        self.trend_system = TrendTradingSystem()
        self.logger = logging.getLogger("MultiTimeframeTrendSystem")
        self.logger.info("多周期趋势系统初始化")
    
    def analyze_multi_timeframe(self, 
                               data_long: pd.DataFrame,  # 长周期数据 (周线/日线)
                               data_mid: pd.DataFrame,   # 中周期数据 (日线/4小时)
                               data_short: pd.DataFrame  # 短周期数据 (4小时/1小时)
                               ) -> Dict:
        """分析多周期趋势"""
        # 分析长周期趋势 (主趋势)
        long_trend = self.trend_system.analyze_ema_trend(data_long, 
                                                       short_period=6, 
                                                       mid_period=10, 
                                                       long_period=20)
        
        # 分析中周期趋势
        mid_trend = self.trend_system.analyze_ema_trend(data_mid, 
                                                      short_period=20, 
                                                      mid_period=50, 
                                                      long_period=100)
        
        # 分析短周期趋势 (入场时机)
        short_trend = self.trend_system.analyze_ema_trend(data_short, 
                                                        short_period=5, 
                                                        mid_period=20, 
                                                        long_period=50)
        
        # 记录各周期趋势
        self.logger.info(f"长周期趋势: {long_trend.value}")
        self.logger.info(f"中周期趋势: {mid_trend.value}")
        self.logger.info(f"短周期趋势: {short_trend.value}")
        
        # 判断趋势一致性
        trends_aligned = (
            (long_trend == TrendDirection.UPTREND and 
             mid_trend == TrendDirection.UPTREND and 
             short_trend == TrendDirection.UPTREND) or
            (long_trend == TrendDirection.DOWNTREND and 
             mid_trend == TrendDirection.DOWNTREND and 
             short_trend == TrendDirection.DOWNTREND)
        )
        
        # 根据短周期生成具体信号
        if trends_aligned:
            signal = self.trend_system.execute_strategy(data_short)
            signal["trend_aligned"] = True
        else:
            # 如果趋势不一致，只有在主趋势和中周期趋势一致时才考虑交易
            if (long_trend == mid_trend and 
                ((long_trend == TrendDirection.UPTREND and short_trend != TrendDirection.DOWNTREND) or
                 (long_trend == TrendDirection.DOWNTREND and short_trend != TrendDirection.UPTREND))):
                signal = self.trend_system.execute_strategy(data_short)
                signal["trend_aligned"] = False
            else:
                signal = {"signal": SignalType.HOLD.value, "trend_aligned": False}
        
        signal.update({
            "long_trend": long_trend.value,
            "mid_trend": mid_trend.value,
            "short_trend": short_trend.value
        })
        
        return signal

    def backtest_strategy(self, 
                        data_long: pd.DataFrame,
                        data_mid: pd.DataFrame,
                        data_short: pd.DataFrame,
                        initial_capital: float = 10000.0) -> Dict:
        """回测多周期趋势策略"""
        # 初始化回测结果
        results = {
            "trades": [],
            "capital": initial_capital,
            "max_drawdown": 0,
            "win_rate": 0,
            "profit_factor": 0
        }
        
        # 当前持仓
        position = 0
        entry_price = 0
        
        # 统计指标
        wins = 0
        losses = 0
        gross_profit = 0
        gross_loss = 0
        max_capital = initial_capital
        
        # 每个短周期进行分析
        for i in range(100, len(data_short)):
            # 截取数据
            current_long = data_long.iloc[:i//5]  # 假设长周期是短周期的5倍
            current_mid = data_mid.iloc[:i//2]    # 假设中周期是短周期的2倍
            current_short = data_short.iloc[:i]
            
            # 生成信号
            signal = self.analyze_multi_timeframe(current_long, current_mid, current_short)
            current_price = current_short['close'].iloc[-1]
            
            # 交易逻辑
            if position == 0:  # 无持仓
                if signal["signal"] == SignalType.BUY.value and signal["trend_aligned"]:
                    # 买入信号
                    position = signal["position_size"]
                    entry_price = current_price
                    results["trades"].append({
                        "type": "买入",
                        "price": current_price,
                        "size": position,
                        "timestamp": current_short.index[-1]
                    })
                elif signal["signal"] == SignalType.SELL.value and signal["trend_aligned"]:
                    # 卖出信号 (做空)
                    position = -signal["position_size"]
                    entry_price = current_price
                    results["trades"].append({
                        "type": "卖出",
                        "price": current_price,
                        "size": position,
                        "timestamp": current_short.index[-1]
                    })
            elif position > 0:  # 多头持仓
                if signal["signal"] == SignalType.SELL.value or (
                    current_price <= signal["stop_loss"] or current_price >= signal["take_profit"]):
                    # 平仓
                    profit = (current_price - entry_price) * position
                    results["capital"] += profit
                    
                    # 更新统计指标
                    if profit > 0:
                        wins += 1
                        gross_profit += profit
                    else:
                        losses += 1
                        gross_loss -= profit
                    
                    # 记录交易
                    results["trades"].append({
                        "type": "平多",
                        "price": current_price,
                        "size": position,
                        "profit": profit,
                        "timestamp": current_short.index[-1]
                    })
                    
                    position = 0
            elif position < 0:  # 空头持仓
                if signal["signal"] == SignalType.BUY.value or (
                    current_price >= signal["stop_loss"] or current_price <= signal["take_profit"]):
                    # 平仓
                    profit = (entry_price - current_price) * abs(position)
                    results["capital"] += profit
                    
                    # 更新统计指标
                    if profit > 0:
                        wins += 1
                        gross_profit += profit
                    else:
                        losses += 1
                        gross_loss -= profit
                    
                    # 记录交易
                    results["trades"].append({
                        "type": "平空",
                        "price": current_price,
                        "size": abs(position),
                        "profit": profit,
                        "timestamp": current_short.index[-1]
                    })
                    
                    position = 0
            
            # 更新最大资金和回撤
            max_capital = max(max_capital, results["capital"])
            current_drawdown = (max_capital - results["capital"]) / max_capital if max_capital > 0 else 0
            results["max_drawdown"] = max(results["max_drawdown"], current_drawdown)
        
        # 计算胜率和盈亏比
        total_trades = wins + losses
        results["win_rate"] = wins / total_trades if total_trades > 0 else 0
        results["profit_factor"] = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        return results

if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建趋势交易系统
    trend_system = MultiTimeframeTrendSystem()
    logger = logging.getLogger("TrendTest")
    
    logger.info("多指标组合趋势交易系统已创建") 