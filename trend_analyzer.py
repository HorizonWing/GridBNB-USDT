import asyncio
import logging
import json
import os
import platform
import sys
import argparse
import numpy as np
from helpers import send_pushplus_message, format_signal_message
from config import ENABLE_SIGNAL_PUSH
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

# Windows平台事件循环兼容
if platform.system() == 'Windows':
    import asyncio
    if sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from trend_analyzer_runner import TrendAnalyzerRunner
from trend_trading_system import (
    MultiTimeframeTrendSystem,
    TimeFrame,
    SignalType,
    TrendDirection
)

class PositionManager:
    """仓位管理器"""
    def __init__(self, initial_balance: float = 10000.0, risk_per_trade: float = 0.02):
        self.balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.current_position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        
    def calculate_position_size(self, atr: float, entry_price: float) -> float:
        """根据ATR计算仓位大小"""
        risk_amount = self.balance * self.risk_per_trade
        position_size = risk_amount / (atr * 2)  # 使用2倍ATR作为止损距离
        return min(position_size, self.balance / entry_price)  # 确保不超过账户余额
        
    def update_position(self, position_type: str, entry_price: float, atr: float):
        """更新仓位信息"""
        self.current_position = position_type
        self.entry_price = entry_price
        position_size = self.calculate_position_size(atr, entry_price)
        
        if position_type == 'long':
            self.stop_loss = entry_price - atr * 2
            self.take_profit = entry_price + atr * 3
        else:  # short
            self.stop_loss = entry_price + atr * 2
            self.take_profit = entry_price - atr * 3
            
        return position_size
        
    def should_close_position(self, current_price: float) -> bool:
        """检查是否需要平仓"""
        if not self.current_position:
            return False
            
        if self.current_position == 'long':
            return current_price <= self.stop_loss or current_price >= self.take_profit
        else:  # short
            return current_price >= self.stop_loss or current_price <= self.take_profit

class TrendAnalyzer:
    """趋势分析与交易信号整合系统"""
    
    def __init__(self,
                exchange_id: str = 'binance',
                symbol: str = 'BTC/USDT',
                simulation_mode: bool = True,
                proxy: str = None,
                check_interval: int = 300,
                output_dir: str = 'trend_signals'):
        """
        初始化趋势主系统
        
        Args:
            exchange_id: 交易所ID
            symbol: 交易对
            simulation_mode: 是否使用模拟模式
            proxy: 代理地址
            check_interval: 检查间隔（秒）
            output_dir: 输出目录
        """
        self.logger = self._setup_logger()
        self.exchange_id = exchange_id
        self.symbol = symbol
        self.simulation_mode = simulation_mode
        self.proxy = proxy
        self.check_interval = check_interval
        self.output_dir = output_dir
        
        # 确保输出目录存在
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # 创建趋势分析器实例
        self.analyzer = TrendAnalyzerRunner(
            exchange_id=exchange_id,
            symbol=symbol,
            simulation_mode=simulation_mode,
            proxy=proxy,
            interval=check_interval
        )
        
        # 最近一次分析结果
        self.last_result = None
        self.last_signal = None
        self.is_running = False
        
        # 添加仓位管理器
        self.position_manager = PositionManager()
        
        # 添加ATR计算相关参数
        self.atr_period = 14
        self.atr_multiplier = 2.0
        
        self.logger.info(f"趋势主系统初始化完成 - 交易对: {symbol}, 模式: {'模拟' if simulation_mode else '实盘'}")
    
    def _setup_logger(self):
        """设置日志"""
        logger = logging.getLogger("TrendMain")
        logger.setLevel(logging.INFO)
        
        # 创建文件处理器
        file_handler = logging.FileHandler("trend_main.log")
        file_handler.setLevel(logging.INFO)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 创建格式器
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器到日志器
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    def _should_send_notification(self, current_signal: Dict) -> bool:
        """
        判断是否需要发送通知
        
        Args:
            current_signal: 当前信号数据
            
        Returns:
            bool: 如果信号发生变化返回True，否则返回False
        """
        if self.last_signal is None:
            return True
            
        # 比较关键信息是否发生变化
        key_fields = ['signal', 'advice', 'confidence', 'market_state']
        for field in key_fields:
            if current_signal.get(field) != self.last_signal.get(field):
                return True
                
        return False

    def calculate_atr(self, high_prices: List[float], low_prices: List[float], close_prices: List[float]) -> float:
        """计算ATR"""
        if len(high_prices) < self.atr_period:
            return 0.0
            
        tr = []
        for i in range(1, len(high_prices)):
            tr1 = high_prices[i] - low_prices[i]
            tr2 = abs(high_prices[i] - close_prices[i-1])
            tr3 = abs(low_prices[i] - close_prices[i-1])
            tr.append(max(tr1, tr2, tr3))
            
        return np.mean(tr[-self.atr_period:])
    
    def is_consolidation(self, prices: List[float], atr: float) -> bool:
        """判断是否处于震荡行情"""
        if len(prices) < 20:
            return False
            
        # 计算价格波动范围
        price_range = max(prices[-20:]) - min(prices[-20:])
        # 如果价格波动范围小于2倍ATR，认为是震荡行情
        return price_range < atr * 2
    
    async def execute_trade(self, signal: Dict):
        """执行交易"""
        try:
            current_price = signal.get('current_price', 0)
            atr = signal.get('atr', 0)
            position_ratio = signal.get('position_ratio', 0)
            
            # 检查是否需要平仓
            if signal.get('should_close', False):
                if self.position_manager.current_position:
                    self.logger.info(f"执行平仓 - 原因: {signal.get('close_reason', '未知')}")
                    # 这里添加实际的平仓逻辑
                    self.position_manager.current_position = None
                    self.position_manager.entry_price = None
                    self.position_manager.stop_loss = None
                    self.position_manager.take_profit = None
            
            # 检查是否需要开仓
            elif position_ratio > 0:
                advice = signal.get('advice', '')
                if '买入' in advice and (not self.position_manager.current_position or self.position_manager.current_position == 'short'):
                    # 开多仓
                    position_size = self.position_manager.update_position('long', current_price, atr)
                    self.logger.info(f"执行开多仓 - 价格: {current_price}, 仓位: {position_size}")
                    # 这里添加实际的开多仓逻辑
                    
                elif '卖出' in advice and (not self.position_manager.current_position or self.position_manager.current_position == 'long'):
                    # 开空仓
                    position_size = self.position_manager.update_position('short', current_price, atr)
                    self.logger.info(f"执行开空仓 - 价格: {current_price}, 仓位: {position_size}")
                    # 这里添加实际的开空仓逻辑
                    
        except Exception as e:
            self.logger.error(f"执行交易失败: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())

    async def run_analysis(self) -> Dict:
        """运行一次趋势分析并返回结果"""
        self.logger.info(f"开始趋势分析 - {self.symbol}")
        
        try:
            result = await self.analyzer.run_once(self.output_dir)
            self.last_result = result
            
            # 生成更详细的交易信号
            enhanced_signal = self.enhance_signal(result)

            # 执行交易
            await self.execute_trade(enhanced_signal)

            # 只在信号发生变化时发送通知
            if ENABLE_SIGNAL_PUSH and self._should_send_notification(enhanced_signal):
                message = format_signal_message(enhanced_signal)
                send_pushplus_message(message)
                self.logger.info("检测到信号变化，已发送通知")
            else:
                self.logger.info("信号未发生变化，跳过通知")

            # 更新上一次信号
            self.last_signal = enhanced_signal.copy()

            # 保存增强的信号
            self.save_enhanced_signal(enhanced_signal)
            
            return enhanced_signal
            
        except Exception as e:
            self.logger.error(f"趋势分析失败: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            raise
    
    def enhance_signal(self, result: Dict) -> Dict:
        """根据分析结果增强交易信号"""
        signal_type = result.get('signal', SignalType.HOLD.value)
        trend_aligned = result.get('trend_aligned', False)
        short_trend = result.get('short_trend', TrendDirection.SIDEWAYS.value)
        
        # 获取价格数据
        high_prices = result.get('high_prices', [])
        low_prices = result.get('low_prices', [])
        close_prices = result.get('close_prices', [])
        current_price = close_prices[-1] if close_prices else 0
        
        # 计算ATR
        atr = self.calculate_atr(high_prices, low_prices, close_prices)
        
        # 判断是否处于震荡行情
        is_consolidating = self.is_consolidation(close_prices, atr)
        
        # 创建增强信号字典
        enhanced = result.copy()
        
        # 添加交易信号和建议
        if signal_type == SignalType.BUY.value:
            if trend_aligned:
                enhanced['advice'] = "强烈建议买入"
                enhanced['position_ratio'] = 0.5
                enhanced['confidence'] = "高"
            elif is_consolidating and short_trend == TrendDirection.UPTREND.value:
                enhanced['advice'] = "震荡行情，逢低买入"
                enhanced['position_ratio'] = 0.3
                enhanced['confidence'] = "中"
            else:
                enhanced['advice'] = "建议小仓位买入"
                enhanced['position_ratio'] = 0.2
                enhanced['confidence'] = "中"
        elif signal_type == SignalType.SELL.value:
            if trend_aligned:
                enhanced['advice'] = "强烈建议卖出"
                enhanced['position_ratio'] = 0.5
                enhanced['confidence'] = "高"
            elif is_consolidating and short_trend == TrendDirection.DOWNTREND.value:
                enhanced['advice'] = "震荡行情，逢高卖出"
                enhanced['position_ratio'] = 0.3
                enhanced['confidence'] = "中"
            else:
                enhanced['advice'] = "建议小仓位卖出"
                enhanced['position_ratio'] = 0.2
                enhanced['confidence'] = "中"
        else:  # HOLD
            enhanced['advice'] = "建议观望"
            enhanced['position_ratio'] = 0.0
            enhanced['confidence'] = "低"
        
        # 添加ATR信息
        enhanced['atr'] = atr
        enhanced['is_consolidating'] = is_consolidating
        
        # 检查是否需要平仓
        if self.position_manager.current_position:
            if self.position_manager.should_close_position(current_price):
                enhanced['should_close'] = True
                enhanced['close_reason'] = "达到止损或止盈"
            else:
                enhanced['should_close'] = False
        
        # 添加市场状态总结
        market_state = self.summarize_market_state(result)
        enhanced['market_state'] = market_state
        
        # 记录增强信号
        self.logger.info(f"增强交易信号 - {self.symbol}:")
        self.logger.info(f"信号类型: {signal_type}")
        self.logger.info(f"建议操作: {enhanced['advice']}")
        self.logger.info(f"建议仓位: {enhanced['position_ratio']}")
        self.logger.info(f"信号置信度: {enhanced['confidence']}")
        self.logger.info(f"ATR: {atr}")
        self.logger.info(f"是否震荡: {is_consolidating}")
        self.logger.info(f"市场状态: {market_state}")
        
        return enhanced
    
    def summarize_market_state(self, result: Dict) -> str:
        """根据分析结果总结市场状态"""
        long_trend = result.get('long_trend', TrendDirection.SIDEWAYS.value)
        mid_trend = result.get('mid_trend', TrendDirection.SIDEWAYS.value)
        short_trend = result.get('short_trend', TrendDirection.SIDEWAYS.value)
        
        # 所有趋势都一致
        if long_trend == mid_trend == short_trend:
            if long_trend == TrendDirection.UPTREND.value:
                return "强势上涨，多头市场"
            elif long_trend == TrendDirection.DOWNTREND.value:
                return "强势下跌，空头市场"
            else:
                return "各周期均横盘，盘整市场"
        
        # 长中期趋势一致，短期不同
        if long_trend == mid_trend:
            if long_trend == TrendDirection.UPTREND.value:
                if short_trend == TrendDirection.DOWNTREND.value:
                    return "中长期上涨，短期回调"
                else:
                    return "中长期上涨，短期盘整"
            elif long_trend == TrendDirection.DOWNTREND.value:
                if short_trend == TrendDirection.UPTREND.value:
                    return "中长期下跌，短期反弹"
                else:
                    return "中长期下跌，短期盘整"
            else:  # 中长期盘整
                if short_trend == TrendDirection.UPTREND.value:
                    return "中长期盘整，短期上涨"
                else:
                    return "中长期盘整，短期下跌"
        
        # 其他情况
        if short_trend == TrendDirection.UPTREND.value and mid_trend == TrendDirection.UPTREND.value:
            return "短中期上涨，可能是趋势初期"
        elif short_trend == TrendDirection.DOWNTREND.value and mid_trend == TrendDirection.DOWNTREND.value:
            return "短中期下跌，可能是趋势初期"
        
        # 趋势混合
        return "趋势不明确，建议谨慎"
    
    def save_enhanced_signal(self, signal: Dict):
        """保存增强信号到文件"""
        try:
            # 准备文件名
            symbol_safe = self.symbol.replace('/', '_')
            signal_file = f"{self.output_dir}/{symbol_safe}_signal.json"
            history_file = f"{self.output_dir}/{symbol_safe}_signal_history.json"
            
            # 保存最新信号
            with open(signal_file, 'w', encoding='utf-8') as f:
                json.dump(signal, f, ensure_ascii=False, indent=2)
            
            # 更新历史记录
            history = []
            if os.path.exists(history_file):
                try:
                    with open(history_file, 'r', encoding='utf-8') as f:
                        history = json.load(f)
                        if not isinstance(history, list):
                            history = []
                except Exception:
                    history = []
            
            # 添加当前信号到历史
            history.append(signal)
            
            # 保留最近的100条记录
            if len(history) > 100:
                history = history[-100:]
            
            # 保存历史记录
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"增强信号已保存到 {signal_file}")
            
        except Exception as e:
            self.logger.error(f"保存增强信号失败: {str(e)}")
    
    async def run_continuous(self):
        """持续运行趋势分析"""
        self.is_running = True
        
        self.logger.info(f"启动持续趋势分析 - 检测间隔: {self.check_interval}秒")
        
        try:
            while self.is_running:
                start_time = datetime.now()
                self.logger.info(f"开始新一轮分析 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                try:
                    await self.run_analysis()
                except Exception as e:
                    self.logger.error(f"分析过程中出错: {str(e)}")
                
                # 计算下一次分析时间
                elapsed = (datetime.now() - start_time).total_seconds()
                wait_time = max(0, self.check_interval - elapsed)
                
                if wait_time > 0 and self.is_running:
                    next_time = datetime.now() + timedelta(seconds=wait_time)
                    self.logger.info(f"等待 {wait_time:.1f} 秒进行下一轮分析，预计时间: {next_time.strftime('%H:%M:%S')}")
                    await asyncio.sleep(wait_time)
        
        except asyncio.CancelledError:
            self.logger.info("持续分析已被取消")
            self.is_running = False
        except Exception as e:
            self.logger.error(f"持续分析出错: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            raise
        finally:
            self.is_running = False
            self.logger.info("持续分析已停止")
    
    async def stop(self):
        """停止持续分析"""
        self.is_running = False
        self.logger.info("正在停止持续分析...")

async def start_trend_analyzer(symbol: str = 'BTC/USDT',
                              output_dir: str = 'trend_signals',
                              simulation_mode: bool = True,
                              proxy: str = None,
                              interval: int = 60,
                              continuous: bool = True):
    # 设置命令行参数
    parser = argparse.ArgumentParser(description='趋势分析与交易信号整合系统')
    parser.add_argument('--exchange', type=str, default='binance', help='交易所ID (默认: binance)')
    parser.add_argument('--symbol', type=str, default=symbol, help='交易对 (默认: BTC/USDT)')
    parser.add_argument('--output', type=str, default=output_dir, help='输出目录 (默认: trend_signals)')
    parser.add_argument('--simulation', action='store_true', default=simulation_mode, help='使用模拟数据模式')
    parser.add_argument('--proxy', type=str, default=proxy, help='HTTP/HTTPS代理地址 (例如: http://127.0.0.1:7890)')
    parser.add_argument('--continuous', action='store_true', default=continuous, help='启用持续监控模式')
    parser.add_argument('--interval', type=int, default=interval, help='持续监控模式下的检测间隔(秒) (默认: 60)')
    args = parser.parse_args()
    
    # 创建趋势主系统实例
    trend_analyzer = TrendAnalyzer(
        exchange_id=args.exchange,
        symbol=args.symbol,
        simulation_mode=args.simulation,
        proxy=args.proxy,
        check_interval=args.interval,
        output_dir=args.output
    )
    
    try:
        if args.continuous:
            # 持续模式
            await trend_analyzer.run_continuous()
        else:
            # 单次分析
            await trend_analyzer.run_analysis()
        
    except KeyboardInterrupt:
        print("\n检测到用户中断，正在停止...")
    except Exception as e:
        print(f"运行过程中出错: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 确保正确关闭
        if args.continuous and trend_analyzer.is_running:
            await trend_analyzer.stop()

async def main():
    await start_trend_analyzer()

if __name__ == "__main__":
    # Windows平台事件循环兼容
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main()) 