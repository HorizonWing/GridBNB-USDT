import asyncio
import logging
import json
import os
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Union

from exchange_client import ExchangeClient
from trend_analyzer import TrendAnalyzer
from trend_trading_system import TimeFrame, SignalType, TrendDirection
from order_tracker import OrderTracker
from config import TradingConfig
from helpers import send_pushplus_message, format_trade_message

class TrendTrader:
    """短线趋势跟踪合约交易系统"""
    
    def __init__(self, exchange: ExchangeClient, config: TradingConfig):
        """
        初始化趋势交易系统
        
        Args:
            exchange: 交易所客户端实例
            config: 交易配置实例
        """
        self.exchange = exchange
        self.config = config
        self.symbol = config.SYMBOL
        self.logger = logging.getLogger("TrendTrader")
        
        # 解析交易对的币种
        self.base_currency = self.symbol.split('/')[0] if '/' in self.symbol else 'BTC'
        self.quote_currency = self.symbol.split('/')[1] if '/' in self.symbol else 'USDT'
        
        # 初始化趋势分析器
        self.trend_analyzer = TrendAnalyzer(
            exchange_id=exchange.exchange.id,
            symbol=self.symbol,
            simulation_mode=False,  # 实盘模式
            proxy=None,
            check_interval=config.TREND_INTERVAL,
            output_dir=config.TREND_OUTPUT_DIR
        )
        
        # 订单跟踪
        self.order_tracker = OrderTracker()
        
        # 交易状态
        self.current_position = None  # 'long', 'short', None
        self.position_size = 0.0
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.last_signal = None
        self.is_running = False
        self.current_atr = None
        
        # 风控参数
        self.risk_per_trade = 0.02  # 每笔交易风险2%
        self.atr_period = 14  # ATR周期
        self.sl_atr_multiplier = 2.0  # 止损ATR乘数
        self.tp_atr_multiplier = 3.0  # 止盈ATR乘数
        
        # 价格数据缓存
        self.price_data = {
            '15m': {
                'timestamp': [],
                'open': [],
                'high': [],
                'low': [],
                'close': []
            }
        }
        
        self.logger.info(f"趋势交易系统初始化完成 - 交易对: {self.symbol}")
    
    async def initialize(self):
        """初始化系统，加载市场数据和历史订单"""
        try:
            self.logger.info("正在初始化趋势交易系统...")
            
            # 确保市场数据加载成功
            if not self.exchange.markets_loaded:
                await self.exchange.load_markets()
                
            # 设置初始状态 - 假设没有合约持仓
            self.current_position = None
            self.position_size = 0.0
            self.entry_price = None
            self.stop_loss = None
            self.take_profit = None
            
            # 获取账户余额
            try:
                balance = await self.exchange.fetch_balance()
                if balance and (balance.get('free') or balance.get('total')):
                    self.logger.info(f"账户余额: {balance}")
                else:
                    self.logger.warning("获取账户余额失败，返回了空余额")
            except Exception as e:
                self.logger.warning(f"获取账户余额时发生错误: {str(e)}")
            
            # 尝试获取当前持仓
            try:
                positions = await self.exchange.fetch_positions(symbols=[self.symbol])
                
                # 检查持仓结果
                if positions and len(positions) > 0 and positions[0].get('contracts', 0) > 0:
                    side = positions[0]['side']
                    self.current_position = 'long' if side == 'long' else 'short'
                    self.position_size = positions[0]['contracts']
                    self.entry_price = positions[0]['entryPrice']
                    self.logger.info(f"当前持仓: {self.current_position}, 大小: {self.position_size}, 入场价: {self.entry_price}")
                    
                    # 计算当前ATR以设置止损和止盈
                    await self.update_price_data()
                    await self.calculate_atr()
                    
                    if self.current_atr:
                        self.set_stop_loss_take_profit()
                        self.logger.info(f"设置止损: {self.stop_loss}, 止盈: {self.take_profit}")
                else:
                    self.logger.info("当前无合约持仓")
            except Exception as e:
                error_str = str(e)
                if "Invalid API-key" in error_str or "IP, or permissions" in error_str:
                    self.logger.warning("API权限不足，无法获取合约持仓信息。系统将以无持仓状态运行。")
                    self.logger.warning("如需使用合约交易功能，请确保API密钥有合约交易权限，且已开启IP白名单")
                else:
                    self.logger.warning(f"获取持仓信息失败，将继续但不加载持仓数据: {str(e)}")
            
            # 无论权限如何，都初始化趋势分析器
            try:
                await self.trend_analyzer.run_analysis()
                self.logger.info("趋势分析器初始化成功")
            except Exception as e:
                self.logger.warning(f"趋势分析器初始化失败，但继续运行: {str(e)}")
            
            # 获取初始ATR
            try:
                await self.update_price_data()
                await self.calculate_atr()
                if self.current_atr:
                    self.logger.info(f"当前ATR值: {self.current_atr}")
            except Exception as e:
                self.logger.warning(f"计算初始ATR失败: {str(e)}")
            
            self.logger.info("趋势交易系统初始化完成")
            return True
        
        except Exception as e:
            self.logger.error(f"初始化失败: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    async def update_price_data(self, timeframe: str = '15m', limit: int = 100):
        """更新价格数据"""
        try:
            # 获取K线数据
            ohlcv = await self.exchange.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=limit)
            
            # 更新价格数据缓存
            self.price_data[timeframe]['timestamp'] = [candle[0] for candle in ohlcv]
            self.price_data[timeframe]['open'] = [candle[1] for candle in ohlcv]
            self.price_data[timeframe]['high'] = [candle[2] for candle in ohlcv]
            self.price_data[timeframe]['low'] = [candle[3] for candle in ohlcv]
            self.price_data[timeframe]['close'] = [candle[4] for candle in ohlcv]
            
            self.logger.debug(f"更新{timeframe}价格数据, 最新价格: {self.price_data[timeframe]['close'][-1]}")
            return True
        
        except Exception as e:
            self.logger.error(f"更新价格数据失败: {str(e)}")
            return False
    
    async def calculate_atr(self, timeframe: str = '15m'):
        """计算ATR"""
        try:
            if not self.price_data[timeframe]['high']:
                await self.update_price_data(timeframe)
            
            if len(self.price_data[timeframe]['high']) < self.atr_period + 1:
                self.logger.warning(f"数据不足以计算ATR, 需要至少{self.atr_period + 1}根K线")
                return None
            
            # 转换为numpy数组以便计算
            high = np.array(self.price_data[timeframe]['high'])
            low = np.array(self.price_data[timeframe]['low'])
            close = np.array(self.price_data[timeframe]['close'])
            
            # 计算真实范围TR
            tr1 = high[1:] - low[1:]
            tr2 = np.abs(high[1:] - close[:-1])
            tr3 = np.abs(low[1:] - close[:-1])
            
            # 计算真实范围
            tr = np.maximum(np.maximum(tr1, tr2), tr3)
            
            # 计算ATR (简单移动平均)
            self.current_atr = np.mean(tr[-self.atr_period:])
            
            self.logger.debug(f"ATR计算结果: {self.current_atr}")
            return self.current_atr
        
        except Exception as e:
            self.logger.error(f"计算ATR失败: {str(e)}")
            return None
    
    def is_consolidation(self, timeframe: str = '15m', lookback: int = 20):
        """判断是否处于震荡行情"""
        try:
            if not self.price_data[timeframe]['close']:
                return False
            
            if len(self.price_data[timeframe]['close']) < lookback:
                return False
            
            # 获取最近的价格数据
            recent_prices = self.price_data[timeframe]['close'][-lookback:]
            
            # 计算波动范围
            price_range = max(recent_prices) - min(recent_prices)
            
            # 计算均价
            avg_price = sum(recent_prices) / len(recent_prices)
            
            # 计算波动率
            volatility = price_range / avg_price
            
            # 如果波动率小于当前ATR的2倍，认为是震荡行情
            if self.current_atr and volatility < (self.current_atr * 2 / avg_price):
                return True
            
            return False
        
        except Exception as e:
            self.logger.error(f"判断震荡行情失败: {str(e)}")
            return False
    
    def set_stop_loss_take_profit(self):
        """根据ATR设置止损和止盈"""
        if not self.current_atr or not self.current_position or not self.entry_price:
            return
        
        if self.current_position == 'long':
            self.stop_loss = self.entry_price - (self.current_atr * self.sl_atr_multiplier)
            self.take_profit = self.entry_price + (self.current_atr * self.tp_atr_multiplier)
        else:  # short
            self.stop_loss = self.entry_price + (self.current_atr * self.sl_atr_multiplier)
            self.take_profit = self.entry_price - (self.current_atr * self.tp_atr_multiplier)
    
    async def calculate_position_size(self, entry_price: float):
        """根据ATR计算合适的仓位大小"""
        try:
            if not self.current_atr:
                await self.calculate_atr()
                
            if not self.current_atr:
                return 0.0
            
            # 获取账户余额
            balance = await self.exchange.fetch_balance()
            usdt_balance = balance.get(self.quote_currency, {}).get('free', 0)
            
            # 计算风险金额
            risk_amount = usdt_balance * self.risk_per_trade
            
            # 计算止损点数
            stop_distance = self.current_atr * self.sl_atr_multiplier
            
            # 计算合约数量
            if stop_distance > 0:
                contracts = risk_amount / stop_distance
                # 转换为合约张数
                market_info = self.exchange.exchange.market(self.symbol)
                contract_size = market_info.get('contractSize', 1)
                contracts_adjusted = contracts / contract_size
                
                # 确保不超过账户可用余额
                max_contracts = (usdt_balance * 0.95) / entry_price
                return min(contracts_adjusted, max_contracts)
            
            return 0.0
        
        except Exception as e:
            self.logger.error(f"计算仓位大小失败: {str(e)}")
            return 0.0
    
    async def check_trend_reversal(self, signal: Dict) -> bool:
        """检查趋势是否发生反转"""
        if not self.current_position:
            return False
        
        # 检查信号类型
        signal_type = signal.get('signal', SignalType.HOLD.value)
        
        # 持有多仓时遇到卖出信号，视为反转
        if self.current_position == 'long' and signal_type == SignalType.SELL.value:
            return True
        
        # 持有空仓时遇到买入信号，视为反转
        if self.current_position == 'short' and signal_type == SignalType.BUY.value:
            return True
        
        # 检查止损和止盈
        current_price = signal.get('current_price', 0)
        if current_price and self.stop_loss and self.take_profit:
            if self.current_position == 'long':
                if current_price <= self.stop_loss or current_price >= self.take_profit:
                    return True
            else:  # short
                if current_price >= self.stop_loss or current_price <= self.take_profit:
                    return True
        
        return False
    
    async def open_position(self, signal: Dict):
        """开仓操作"""
        try:
            signal_type = signal.get('signal', SignalType.HOLD.value)
            if signal_type == SignalType.HOLD.value:
                return
            
            # 获取当前价格
            current_price = signal.get('current_price', 0)
            if not current_price:
                ticker = await self.exchange.fetch_ticker(self.symbol)
                current_price = ticker['last']
            
            # 短线趋势方向
            short_trend = signal.get('short_trend', TrendDirection.SIDEWAYS.value)
            
            # 检查震荡行情
            is_consolidating = self.is_consolidation()
            
            # 判断开仓条件
            should_open_long = False
            should_open_short = False
            
            if signal_type == SignalType.BUY.value:
                if short_trend == TrendDirection.UPTREND.value:
                    # 上升趋势开多
                    should_open_long = True
                elif is_consolidating and short_trend != TrendDirection.DOWNTREND.value:
                    # 震荡行情，逢低开多
                    should_open_long = True
            
            elif signal_type == SignalType.SELL.value:
                if short_trend == TrendDirection.DOWNTREND.value:
                    # 下降趋势开空
                    should_open_short = True
                elif is_consolidating and short_trend != TrendDirection.UPTREND.value:
                    # 震荡行情，逢高开空
                    should_open_short = True
            
            # 若已持仓则不开仓
            if self.current_position:
                return
            
            # 计算仓位大小
            position_size = await self.calculate_position_size(current_price)
            
            # 执行开仓
            if should_open_long:
                self.logger.info(f"开多仓 - 价格: {current_price}, 仓位: {position_size}")
                
                # 执行下单
                order = await self.exchange.create_market_order(
                    symbol=self.symbol,
                    side='buy',
                    amount=position_size,
                    params={'leverage': 3}  # 设置杠杆倍数
                )
                
                if order and order.get('status') == 'closed':
                    self.current_position = 'long'
                    self.position_size = position_size
                    self.entry_price = order.get('price', current_price)
                    self.set_stop_loss_take_profit()
                    
                    # 记录交易
                    self.order_tracker.add_trade({
                        'timestamp': datetime.now().timestamp(),
                        'side': 'buy',
                        'price': self.entry_price,
                        'amount': self.position_size,
                        'stop_loss': self.stop_loss,
                        'take_profit': self.take_profit
                    })
                    
                    # 发送通知
                    trade_message = f"开多仓成功\n价格: {self.entry_price}\n数量: {self.position_size}\n止损: {self.stop_loss}\n止盈: {self.take_profit}"
                    send_pushplus_message(trade_message)
            
            elif should_open_short:
                self.logger.info(f"开空仓 - 价格: {current_price}, 仓位: {position_size}")
                
                # 执行下单
                order = await self.exchange.create_market_order(
                    symbol=self.symbol,
                    side='sell',
                    amount=position_size,
                    params={'leverage': 3}  # 设置杠杆倍数
                )
                
                if order and order.get('status') == 'closed':
                    self.current_position = 'short'
                    self.position_size = position_size
                    self.entry_price = order.get('price', current_price)
                    self.set_stop_loss_take_profit()
                    
                    # 记录交易
                    self.order_tracker.add_trade({
                        'timestamp': datetime.now().timestamp(),
                        'side': 'sell',
                        'price': self.entry_price,
                        'amount': self.position_size,
                        'stop_loss': self.stop_loss,
                        'take_profit': self.take_profit
                    })
                    
                    # 发送通知
                    trade_message = f"开空仓成功\n价格: {self.entry_price}\n数量: {self.position_size}\n止损: {self.stop_loss}\n止盈: {self.take_profit}"
                    send_pushplus_message(trade_message)
        
        except Exception as e:
            self.logger.error(f"开仓失败: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    async def close_position(self, reason: str = "趋势反转"):
        """平仓操作"""
        try:
            if not self.current_position:
                return
            
            # 获取当前价格
            ticker = await self.exchange.fetch_ticker(self.symbol)
            current_price = ticker['last']
            
            side = 'sell' if self.current_position == 'long' else 'buy'
            self.logger.info(f"平仓 - 原因: {reason}, 价格: {current_price}")
            
            # 执行平仓
            order = await self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=self.position_size
            )
            
            if order and order.get('status') == 'closed':
                # 计算盈亏
                pnl = 0
                if self.current_position == 'long':
                    pnl = (current_price - self.entry_price) * self.position_size
                else:
                    pnl = (self.entry_price - current_price) * self.position_size
                
                # 记录交易
                self.order_tracker.add_trade({
                    'timestamp': datetime.now().timestamp(),
                    'side': side,
                    'price': current_price,
                    'amount': self.position_size,
                    'pnl': pnl,
                    'close_reason': reason
                })
                
                # 发送通知
                trade_message = f"平仓成功\n原因: {reason}\n价格: {current_price}\n数量: {self.position_size}\n盈亏: {pnl:.2f}"
                send_pushplus_message(trade_message)
                
                # 重置持仓状态
                self.current_position = None
                self.position_size = 0.0
                self.entry_price = None
                self.stop_loss = None
                self.take_profit = None
        
        except Exception as e:
            self.logger.error(f"平仓失败: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    async def check_position(self):
        """检查当前持仓，如果达到止损或止盈点，执行平仓"""
        try:
            if not self.current_position:
                return
            
            # 获取当前价格
            ticker = await self.exchange.fetch_ticker(self.symbol)
            current_price = ticker['last']
            
            # 检查是否达到止损或止盈
            if self.current_position == 'long':
                if current_price <= self.stop_loss:
                    await self.close_position("止损触发")
                elif current_price >= self.take_profit:
                    await self.close_position("止盈触发")
            else:  # short
                if current_price >= self.stop_loss:
                    await self.close_position("止损触发")
                elif current_price <= self.take_profit:
                    await self.close_position("止盈触发")
        
        except Exception as e:
            self.logger.error(f"检查持仓失败: {str(e)}")
    
    async def trading_loop(self):
        """主交易循环"""
        self.is_running = True
        
        self.logger.info(f"启动趋势交易循环 - 交易对: {self.symbol}")
        
        # 检查API权限
        has_futures_permission = True
        try:
            # 尝试获取合约持仓，测试API权限
            positions = await self.exchange.fetch_positions(symbols=[self.symbol])
            self.logger.info("API权限检查: 合约交易权限正常，将执行完整的交易功能")
        except Exception as e:
            error_str = str(e)
            if "Invalid API-key" in error_str or "IP, or permissions" in error_str:
                has_futures_permission = False
                self.logger.warning("API权限不足，将只执行趋势分析但不会进行实际交易")
            else:
                self.logger.warning(f"API权限检查过程中发生未知错误: {str(e)}")
        
        try:
            while self.is_running:
                try:
                    # 更新价格数据
                    await self.update_price_data()
                    
                    # 计算ATR
                    await self.calculate_atr()
                    
                    # 运行趋势分析
                    signal = await self.trend_analyzer.run_analysis()
                    
                    # 更新当前价格到信号中
                    if self.price_data['15m']['close']:
                        signal['current_price'] = self.price_data['15m']['close'][-1]
                    
                    # 如果有合约交易权限，执行交易操作
                    if has_futures_permission:
                        # 检查趋势反转
                        if await self.check_trend_reversal(signal):
                            await self.close_position("趋势反转")
                        
                        # 检查开仓条件
                        await self.open_position(signal)
                        
                        # 检查止损止盈
                        await self.check_position()
                    else:
                        # 无合约交易权限，仅记录分析结果
                        signal_type = signal.get('signal', 'hold')
                        price = signal.get('current_price', 0)
                        self.logger.info(f"趋势信号: {signal_type}, 当前价格: {price}（仅分析模式，不执行交易）")
                    
                    # 更新上一次信号
                    self.last_signal = signal
                
                except Exception as e:
                    self.logger.error(f"交易循环遇到错误: {str(e)}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                
                # 等待下一轮
                await asyncio.sleep(self.config.TREND_INTERVAL)
        
        except asyncio.CancelledError:
            self.logger.info("交易循环被取消")
        
        finally:
            self.is_running = False
            self.logger.info("交易循环已停止")
    
    async def stop(self):
        """停止交易"""
        self.is_running = False
        self.logger.info("正在停止趋势交易系统...")
        
        # 关闭趋势分析器
        await self.trend_analyzer.stop()
        
        # 等待任务完成
        await asyncio.sleep(1)

async def run_trend_trader(exchange: ExchangeClient, config: TradingConfig):
    """运行趋势交易系统"""
    try:
        trend_trader = TrendTrader(exchange, config)
        
        # 初始化
        success = await trend_trader.initialize()
        if not success:
            logging.error("趋势交易系统初始化失败")
            return
        
        # 启动交易循环
        await trend_trader.trading_loop()
        
    except Exception as e:
        logging.error(f"趋势交易系统运行错误: {str(e)}")
        import traceback
        logging.error(traceback.format_exc()) 