import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import logging
import numpy as np
import argparse
import os
import json
import sys
import platform
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Union

# Windows平台事件循环兼容
if platform.system() == 'Windows':
    import asyncio
    # 防止重复导入aiohttp内部模块
    if sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from trend_trading_system import (
    MultiTimeframeTrendSystem,
    TimeFrame,
    SignalType,
    TrendDirection
)

class TrendAnalyzerRunner:
    """趋势分析运行器，用于获取市场数据并应用趋势分析"""
    
    def __init__(self, exchange_id: str = 'binance', symbol: str = 'BTC/USDT', simulation_mode: bool = False, proxy: str = None, interval: int = 300):
        self.logger = logging.getLogger("TrendAnalyzerRunner")
        self.exchange_id = exchange_id
        self.symbol = symbol
        self.exchange = None
        self.trend_system = MultiTimeframeTrendSystem()
        self.simulation_mode = simulation_mode
        self.proxy = proxy
        self.interval = interval  # 检测间隔，单位为秒
        self.last_signal = None  # 上一次的信号
        self.is_running = False  # 运行状态标志
        
    async def initialize(self):
        """初始化交易所连接"""
        if not self.simulation_mode:
            self.logger.info(f"初始化交易所连接: {self.exchange_id}")
            
            # 创建交易所实例
            exchange_class = getattr(ccxt, self.exchange_id)
            exchange_config = {
                'enableRateLimit': True,  # 启用请求限制
                'timeout': 30000,         # 设置超时时间为30秒
            }
            
            # 如果指定了代理，添加到配置中
            if self.proxy:
                self.logger.info(f"使用代理: {self.proxy}")
                exchange_config['proxy'] = self.proxy
                exchange_config['httpsProxy'] = self.proxy
                
            self.exchange = exchange_class(exchange_config)
            
            # 检查交易所是否支持该交易对
            await self.exchange.load_markets()
            if self.symbol not in self.exchange.symbols:
                raise ValueError(f"交易所不支持该交易对: {self.symbol}")
                
            self.logger.info(f"交易所连接成功，交易对: {self.symbol}")
        else:
            self.logger.info("使用模拟模式，无需连接交易所")
    
    async def close(self):
        """关闭交易所连接"""
        if self.exchange and not self.simulation_mode:
            await self.exchange.close()
            self.logger.info("交易所连接已关闭")
    
    async def fetch_ohlcv(self, timeframe: str, limit: int = 100) -> pd.DataFrame:
        """获取OHLCV数据"""
        self.logger.info(f"获取 {self.symbol} {timeframe} 周期数据, limit={limit}")
        
        if not self.simulation_mode:
            try:
                # 获取K线数据
                ohlcv = await self.exchange.fetch_ohlcv(self.symbol, timeframe, limit=limit)
                
                # 转换为DataFrame
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                
                return df
                
            except Exception as e:
                self.logger.error(f"获取数据失败: {str(e)}")
                raise
        else:
            # 使用模拟数据
            self.logger.info("使用模拟数据")
            return self.generate_mock_data(timeframe, limit)
    
    def generate_mock_data(self, timeframe: str, limit: int = 100) -> pd.DataFrame:
        """生成模拟的OHLCV数据"""
        
        # 根据不同的时间周期设置起始时间
        if timeframe == TimeFrame.DAY_1.value:
            start_date = datetime.now() - timedelta(days=limit)
            freq = 'D'
        elif timeframe == TimeFrame.HOUR_4.value:
            start_date = datetime.now() - timedelta(hours=limit * 4)
            freq = '4h'
        elif timeframe == TimeFrame.HOUR_1.value:
            start_date = datetime.now() - timedelta(hours=limit)
            freq = '1h'
        else:
            start_date = datetime.now() - timedelta(hours=limit)
            freq = '1h'
        
        # 生成日期范围
        index = pd.date_range(start=start_date, periods=limit, freq=freq)
        
        # 生成模拟价格数据 (使用逼真的BTC价格范围)
        base_price = 65000  # 基础价格
        volatility = 0.02  # 波动率
        
        # 生成价格序列
        prices = [base_price]
        for i in range(1, limit):
            change = random.uniform(-1, 1) * volatility * prices[-1]
            new_price = prices[-1] + change
            prices.append(new_price)
        
        # 创建OHLCV数据
        data = {
            'open': [],
            'high': [],
            'low': [],
            'close': [],
            'volume': []
        }
        
        for i in range(limit):
            open_price = prices[i]
            close_price = open_price * (1 + random.uniform(-0.01, 0.01))
            high_price = max(open_price, close_price) * (1 + random.uniform(0, 0.01))
            low_price = min(open_price, close_price) * (1 - random.uniform(0, 0.01))
            volume = random.uniform(10, 100) * 10
            
            data['open'].append(open_price)
            data['high'].append(high_price)
            data['low'].append(low_price)
            data['close'].append(close_price)
            data['volume'].append(volume)
        
        # 创建DataFrame
        df = pd.DataFrame(data, index=index)
        return df
    
    async def analyze_trend(self):
        """分析趋势并生成信号"""
        try:
            # 获取不同周期的数据
            long_data = await self.fetch_ohlcv(TimeFrame.DAY_1.value, limit=100)  # 日线周期，获取100条
            mid_data = await self.fetch_ohlcv(TimeFrame.HOUR_4.value, limit=100)  # 4小时周期，获取100条
            short_data = await self.fetch_ohlcv(TimeFrame.HOUR_1.value, limit=100)  # 1小时周期，获取100条
            
            # 分析多周期趋势
            signal = self.trend_system.analyze_multi_timeframe(long_data, mid_data, short_data)
            
            # 添加时间戳和交易对信息
            signal['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            signal['symbol'] = self.symbol
            
            return signal
            
        except Exception as e:
            self.logger.error(f"分析趋势失败: {str(e)}")
            raise
    
    def save_result(self, result: Dict, output_dir: str = 'results'):
        """保存分析结果"""
        try:
            # 确保输出目录存在
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # 创建固定文件名和历史文件名
            symbol_safe = self.symbol.replace('/', '_')
            latest_file = f"{output_dir}/{symbol_safe}_latest.json"
            history_file = f"{output_dir}/{symbol_safe}_history.json"
            
            # 添加当前时间戳
            if 'timestamp' not in result:
                result['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 保存最新结果到固定文件
            with open(latest_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            # 更新历史记录
            try:
                if os.path.exists(history_file):
                    with open(history_file, 'r', encoding='utf-8') as f:
                        try:
                            history = json.load(f)
                            if not isinstance(history, list):
                                history = []
                        except:
                            history = []
                else:
                    history = []
                
                # 添加新结果到历史
                history.append(result)
                
                # 限制历史记录数量为100
                if len(history) > 100:
                    history = history[-100:]
                
                # 保存历史记录
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                    
            except Exception as e:
                self.logger.error(f"保存历史记录失败: {str(e)}")
            
            self.logger.info(f"分析结果已保存到 {latest_file}")
            
        except Exception as e:
            self.logger.error(f"保存结果失败: {str(e)}")
    
    async def run_once(self, output_dir: str = 'results'):
        """运行一次趋势分析"""
        try:
            await self.initialize()
            
            result = await self.analyze_trend()
            
            # 输出分析结果
            self.logger.info(f"分析结果:")
            self.logger.info(f"长周期趋势: {result['long_trend']}")
            self.logger.info(f"中周期趋势: {result['mid_trend']}")
            self.logger.info(f"短周期趋势: {result['short_trend']}")
            self.logger.info(f"交易信号: {result['signal']}")
            self.logger.info(f"趋势一致性: {result['trend_aligned']}")
            
            if result['signal'] != SignalType.HOLD.value:
                self.logger.info(f"当前价格: {result['current_price']}")
                if 'stop_loss' in result:
                    self.logger.info(f"止损价格: {result['stop_loss']}")
                if 'take_profit' in result:
                    self.logger.info(f"止盈价格: {result['take_profit']}")
                if 'position_size' in result:
                    self.logger.info(f"建议仓位: {result['position_size']}")
            
            # 信号变化检测
            if self.last_signal and self.last_signal != result['signal']:
                self.logger.info(f"信号变化: {self.last_signal} -> {result['signal']}")
            
            self.last_signal = result['signal']
            
            # 保存结果
            self.save_result(result, output_dir)
            
            return result
            
        finally:
            await self.close()
    
    async def run_continuous(self, output_dir: str = 'results'):
        """持续运行趋势分析"""
        self.is_running = True
        
        self.logger.info(f"启动持续监控，检测间隔: {self.interval}秒")
        
        try:
            while self.is_running:
                start_time = time.time()
                self.logger.info(f"开始新一轮分析 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                try:
                    await self.run_once(output_dir)
                except Exception as e:
                    self.logger.error(f"分析过程中出错: {str(e)}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                
                # 计算运行时间和需要等待的时间
                elapsed = time.time() - start_time
                wait_time = max(0, self.interval - elapsed)
                
                if wait_time > 0 and self.is_running:
                    self.logger.info(f"等待 {wait_time:.1f} 秒进行下一轮分析")
                    await asyncio.sleep(wait_time)
        
        except asyncio.CancelledError:
            self.logger.info("持续监控已被取消")
            self.is_running = False
        except Exception as e:
            self.logger.error(f"持续监控出错: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            raise
        finally:
            self.is_running = False
            self.logger.info("持续监控已停止")
    
    async def stop(self):
        """停止持续监控"""
        self.is_running = False
        self.logger.info("正在停止持续监控...")
    
    async def run(self, output_dir: str = 'results', continuous: bool = False):
        """运行趋势分析，可选择单次或持续运行"""
        if continuous:
            await self.run_continuous(output_dir)
        else:
            await self.run_once(output_dir)

async def main():
    """主函数"""
    # 设置命令行参数
    parser = argparse.ArgumentParser(description='趋势分析运行器')
    parser.add_argument('--exchange', type=str, default='binance', help='交易所ID (默认: binance)')
    parser.add_argument('--symbol', type=str, default='BTC/USDT', help='交易对 (默认: BTC/USDT)')
    parser.add_argument('--output', type=str, default='results', help='输出目录 (默认: results)')
    parser.add_argument('--simulation', action='store_true', help='使用模拟数据模式')
    parser.add_argument('--proxy', type=str, help='HTTP/HTTPS代理地址 (例如: http://127.0.0.1:7890)')
    parser.add_argument('--continuous', action='store_true', help='启用持续监控模式')
    parser.add_argument('--interval', type=int, default=300, help='持续监控模式下的检测间隔(秒) (默认: 300)')
    args = parser.parse_args()
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("trend_analyzer.log"),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger("TrendAnalyzer")
    logger.info("="*50)
    logger.info("开始趋势分析")
    logger.info(f"交易所: {args.exchange}")
    logger.info(f"交易对: {args.symbol}")
    if args.simulation:
        logger.info("模式: 模拟数据")
    if args.proxy:
        logger.info(f"代理: {args.proxy}")
    if args.continuous:
        logger.info(f"持续监控: 是，间隔 {args.interval}秒")
    logger.info("="*50)
    
    try:
        # 创建分析器实例
        analyzer = TrendAnalyzerRunner(args.exchange, args.symbol, args.simulation, args.proxy, args.interval)
        
        # 运行分析
        await analyzer.run(args.output, args.continuous)
        
        if not args.continuous:
            logger.info("趋势分析完成")
        
    except KeyboardInterrupt:
        logger.info("检测到键盘中断，停止分析...")
    except Exception as e:
        logger.error(f"趋势分析失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    # Windows平台事件循环兼容
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main()) 