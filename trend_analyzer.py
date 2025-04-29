import asyncio
import logging
import json
import os
import platform
import sys
import argparse
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
        self.last_signal = None  # 添加上一次信号的记录
        self.is_running = False
        
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

    async def run_analysis(self) -> Dict:
        """运行一次趋势分析并返回结果"""
        self.logger.info(f"开始趋势分析 - {self.symbol}")
        
        try:
            result = await self.analyzer.run_once(self.output_dir)
            self.last_result = result
            
            # 生成更详细的交易信号
            enhanced_signal = self.enhance_signal(result)

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
        
        # 创建增强信号字典
        enhanced = result.copy()
        
        # 添加建议
        if signal_type == SignalType.BUY.value:
            if trend_aligned:
                enhanced['advice'] = "强烈建议买入"
                enhanced['position_ratio'] = 0.5
                enhanced['confidence'] = "高"
            else:
                enhanced['advice'] = "建议小仓位买入"
                enhanced['position_ratio'] = 0.2
                enhanced['confidence'] = "中"
        elif signal_type == SignalType.SELL.value:
            if trend_aligned:
                enhanced['advice'] = "强烈建议卖出"
                enhanced['position_ratio'] = 0.5
                enhanced['confidence'] = "高"
            else:
                enhanced['advice'] = "建议小仓位卖出"
                enhanced['position_ratio'] = 0.2
                enhanced['confidence'] = "中"
        else:  # HOLD
            enhanced['advice'] = "建议观望"
            enhanced['position_ratio'] = 0.0
            enhanced['confidence'] = "低"
        
        # 添加市场状态总结
        market_state = self.summarize_market_state(result)
        enhanced['market_state'] = market_state
        
        # 记录增强信号
        self.logger.info(f"增强交易信号 - {self.symbol}:")
        self.logger.info(f"信号类型: {signal_type}")
        self.logger.info(f"建议操作: {enhanced['advice']}")
        self.logger.info(f"建议仓位: {enhanced['position_ratio']}")
        self.logger.info(f"信号置信度: {enhanced['confidence']}")
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