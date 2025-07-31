import asyncio
import logging
import time
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from config import settings


class SimulationExchange:
    """
    虚拟交易所客户端，模拟真实交易所的接口
    使用真实的市场数据，但买卖操作仅在虚拟环境中执行
    """
    
    def __init__(self, real_exchange):
        """
        初始化虚拟交易所
        
        Args:
            real_exchange: 真实的交易所客户端，用于获取市场数据
        """
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
        self.real_exchange = real_exchange  # 用于获取真实市场数据
        
        # 虚拟账户初始设置
        self.simulation_balances = {
            'free': {},
            'used': {},
            'total': {}
        }
        
        # 虚拟理财账户余额
        self.simulation_funding_balance = {}
        
        # 虚拟订单管理
        self.simulation_orders = {}  # 存储虚拟订单
        self.order_id_counter = 1000000  # 虚拟订单ID计数器
        
        # 虚拟交易历史
        self.simulation_trades = []
        
        # 数据持久化路径
        self.simulation_data_file = os.path.join(os.path.dirname(__file__), 'data', 'simulation_data.json')
        
        # 市场数据代理
        self.markets_loaded = False
        self.exchange = real_exchange.exchange  # 直接使用真实exchange对象获取市场数据
        
        # 初始化虚拟账户
        self._initialize_simulation_account()
        
        # 加载持久化数据
        self._load_simulation_data()
        
        self.logger.info("虚拟交易所初始化完成")

    def _initialize_simulation_account(self):
        """初始化虚拟账户余额"""
        # 根据配置设置初始余额
        initial_usdt = settings.SIMULATION_INITIAL_BALANCE
        
        # 设置初始USDT余额
        self.simulation_balances['free']['USDT'] = initial_usdt
        self.simulation_balances['used']['USDT'] = 0.0
        self.simulation_balances['total']['USDT'] = initial_usdt
        
        # 其他币种初始余额为0
        for asset in ['BNB', 'BTC', 'ETH']:
            self.simulation_balances['free'][asset] = 0.0
            self.simulation_balances['used'][asset] = 0.0
            self.simulation_balances['total'][asset] = 0.0
        
        self.logger.info(f"虚拟账户初始化完成，初始余额: {initial_usdt} USDT")

    def _load_simulation_data(self):
        """从文件加载虚拟交易数据"""
        try:
            if os.path.exists(self.simulation_data_file):
                with open(self.simulation_data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.simulation_balances = data.get('balances', self.simulation_balances)
                    self.simulation_funding_balance = data.get('funding_balance', self.simulation_funding_balance)
                    self.simulation_trades = data.get('trades', self.simulation_trades)
                    self.order_id_counter = data.get('order_id_counter', self.order_id_counter)
                    
                self.logger.info("虚拟交易数据加载完成")
        except Exception as e:
            self.logger.error(f"加载虚拟交易数据失败: {e}")

    def _save_simulation_data(self):
        """保存虚拟交易数据到文件"""
        try:
            os.makedirs(os.path.dirname(self.simulation_data_file), exist_ok=True)
            data = {
                'balances': self.simulation_balances,
                'funding_balance': self.simulation_funding_balance,
                'trades': self.simulation_trades,
                'order_id_counter': self.order_id_counter,
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.simulation_data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.logger.error(f"保存虚拟交易数据失败: {e}")

    # === 市场数据接口（代理到真实交易所） ===
    
    async def load_markets(self):
        """加载市场数据（代理到真实交易所）"""
        await self.real_exchange.load_markets()
        self.markets_loaded = self.real_exchange.markets_loaded
        
    async def fetch_ticker(self, symbol):
        """获取行情数据（代理到真实交易所）"""
        return await self.real_exchange.fetch_ticker(symbol)
        
    async def fetch_order_book(self, symbol, limit=5):
        """获取订单簿（代理到真实交易所）"""
        return await self.real_exchange.fetch_order_book(symbol, limit)
        
    async def fetch_ohlcv(self, symbol, timeframe='1h', limit=100):
        """获取K线数据（代理到真实交易所）"""
        return await self.real_exchange.fetch_ohlcv(symbol, timeframe, limit)

    # === 虚拟账户余额接口 ===
    
    async def fetch_balance(self, params=None):
        """获取虚拟账户余额"""
        # 确保所有数值都是float类型
        balance = {}
        for balance_type in ['free', 'used', 'total']:
            balance[balance_type] = {}
            for asset, amount in self.simulation_balances[balance_type].items():
                balance[balance_type][asset] = float(amount)
        
        return balance
    
    async def fetch_funding_balance(self):
        """获取虚拟理财账户余额"""
        return {asset: float(amount) for asset, amount in self.simulation_funding_balance.items()}

    # === 虚拟交易接口 ===
    
    async def create_order(self, symbol, order_type, side, amount, price=None, params=None):
        """创建虚拟订单"""
        try:
            # 生成虚拟订单ID
            order_id = str(self.order_id_counter)
            self.order_id_counter += 1
            
            # 解析交易对
            base_asset, quote_asset = symbol.split('/')
            
            # 获取当前市场价格
            if price is None:
                ticker = await self.fetch_ticker(symbol)
                price = ticker['last']
            
            # 计算交易总额
            total_cost = float(amount) * float(price)
            
            # 检查余额是否足够
            if side == 'buy':
                available_balance = self.simulation_balances['free'].get(quote_asset, 0)
                if available_balance < total_cost:
                    raise Exception(f"虚拟账户{quote_asset}余额不足。需要: {total_cost:.2f}, 可用: {available_balance:.2f}")
                
                # 冻结计价货币
                self.simulation_balances['free'][quote_asset] -= total_cost
                self.simulation_balances['used'][quote_asset] = self.simulation_balances['used'].get(quote_asset, 0) + total_cost
                
            else:  # sell
                available_balance = self.simulation_balances['free'].get(base_asset, 0)
                if available_balance < float(amount):
                    raise Exception(f"虚拟账户{base_asset}余额不足。需要: {amount}, 可用: {available_balance:.8f}")
                
                # 冻结基础货币
                self.simulation_balances['free'][base_asset] -= float(amount)
                self.simulation_balances['used'][base_asset] = self.simulation_balances['used'].get(base_asset, 0) + float(amount)
            
            # 创建虚拟订单
            order = {
                'id': order_id,
                'symbol': symbol,
                'type': order_type,
                'side': side,
                'amount': float(amount),
                'price': float(price),
                'cost': total_cost,
                'filled': float(amount),  # 虚拟交易立即成交
                'remaining': 0.0,
                'status': 'closed',  # 虚拟订单立即成交
                'timestamp': int(time.time() * 1000),
                'datetime': datetime.now().isoformat(),
                'info': {'simulation': True}
            }
            
            # 立即执行虚拟交易
            await self._execute_simulation_trade(order, base_asset, quote_asset)
            
            self.logger.info(f"虚拟{side}订单执行成功: {amount} {base_asset} @ {price} {quote_asset}")
            
            return order
            
        except Exception as e:
            self.logger.error(f"创建虚拟订单失败: {e}")
            raise

    async def _execute_simulation_trade(self, order, base_asset, quote_asset):
        """执行虚拟交易"""
        side = order['side']
        amount = order['amount']
        price = order['price']
        total_cost = order['cost']
        
        # 初始化余额字典中不存在的资产
        for asset in [base_asset, quote_asset]:
            for balance_type in ['free', 'used', 'total']:
                if asset not in self.simulation_balances[balance_type]:
                    self.simulation_balances[balance_type][asset] = 0.0
        
        if side == 'buy':
            # 买入：从冻结的计价货币转换为基础货币
            self.simulation_balances['used'][quote_asset] -= total_cost
            self.simulation_balances['free'][base_asset] += amount
            self.simulation_balances['total'][base_asset] += amount
            self.simulation_balances['total'][quote_asset] -= total_cost
            
        else:  # sell
            # 卖出：从冻结的基础货币转换为计价货币
            self.simulation_balances['used'][base_asset] -= amount
            self.simulation_balances['free'][quote_asset] += total_cost
            self.simulation_balances['total'][quote_asset] += total_cost
            self.simulation_balances['total'][base_asset] -= amount
        
        # 记录交易历史
        trade = {
            'id': f"trade_{len(self.simulation_trades) + 1}",
            'order': order['id'],
            'symbol': order['symbol'],
            'side': side,
            'amount': amount,
            'price': price,
            'cost': total_cost,
            'timestamp': order['timestamp'],
            'datetime': order['datetime'],
            'simulation': True
        }
        
        self.simulation_trades.append(trade)
        
        # 保存数据
        self._save_simulation_data()

    async def fetch_order(self, order_id, symbol=None):
        """获取虚拟订单信息（虚拟订单都是立即成交的）"""
        # 虚拟交易中所有订单都立即成交
        return {
            'id': order_id,
            'status': 'closed',
            'filled': 0,  # 这个值会在实际使用中被正确设置
            'remaining': 0,
            'timestamp': int(time.time() * 1000),
            'simulation': True
        }

    async def cancel_order(self, order_id, symbol=None, params=None):
        """取消虚拟订单（虚拟交易中不需要取消，因为立即成交）"""
        self.logger.info(f"虚拟订单 {order_id} 取消请求（虚拟订单立即成交，无需取消）")
        return True

    async def fetch_my_trades(self, symbol, limit=10):
        """获取虚拟交易历史"""
        # 过滤指定交易对的交易记录
        symbol_trades = [trade for trade in self.simulation_trades if trade['symbol'] == symbol]
        # 返回最近的交易记录
        return symbol_trades[-limit:] if len(symbol_trades) > limit else symbol_trades

    # === 虚拟理财接口 ===
    
    async def transfer_to_spot(self, asset, amount):
        """从虚拟理财赎回到现货账户"""
        try:
            # 检查理财余额
            funding_balance = self.simulation_funding_balance.get(asset, 0)
            if funding_balance < amount:
                raise Exception(f"虚拟理财账户{asset}余额不足。需要: {amount}, 可用: {funding_balance}")
            
            # 从理财扣除
            self.simulation_funding_balance[asset] = funding_balance - amount
            
            # 添加到现货
            if asset not in self.simulation_balances['free']:
                self.simulation_balances['free'][asset] = 0.0
                self.simulation_balances['used'][asset] = 0.0
                self.simulation_balances['total'][asset] = 0.0
                
            self.simulation_balances['free'][asset] += amount
            self.simulation_balances['total'][asset] += amount
            
            self._save_simulation_data()
            self.logger.info(f"虚拟理财赎回成功: {amount} {asset}")
            
            return {'success': True, 'amount': amount, 'asset': asset}
            
        except Exception as e:
            self.logger.error(f"虚拟理财赎回失败: {e}")
            raise

    async def transfer_to_savings(self, asset, amount):
        """从现货账户申购虚拟理财"""
        try:
            # 检查现货余额
            spot_balance = self.simulation_balances['free'].get(asset, 0)
            if spot_balance < amount:
                raise Exception(f"虚拟现货账户{asset}余额不足。需要: {amount}, 可用: {spot_balance}")
            
            # 从现货扣除
            self.simulation_balances['free'][asset] -= amount
            self.simulation_balances['total'][asset] -= amount
            
            # 添加到理财
            if asset not in self.simulation_funding_balance:
                self.simulation_funding_balance[asset] = 0.0
            self.simulation_funding_balance[asset] += amount
            
            self._save_simulation_data()
            self.logger.info(f"虚拟理财申购成功: {amount} {asset}")
            
            return {'success': True, 'amount': amount, 'asset': asset}
            
        except Exception as e:
            self.logger.error(f"虚拟理财申购失败: {e}")
            raise

    # === 其他必要接口 ===
    
    async def fetch_open_orders(self, symbol=None):
        """获取未成交订单（虚拟交易中都是立即成交，所以返回空列表）"""
        return []

    async def close(self):
        """关闭虚拟交易所连接"""
        self._save_simulation_data()
        self.logger.info("虚拟交易所连接已关闭")

    async def calculate_total_account_value(self, quote_currency: str = 'USDT') -> float:
        """计算虚拟账户总资产价值"""
        try:
            total_value = 0.0
            
            # 计算现货资产价值
            for asset, amount in self.simulation_balances['total'].items():
                if amount > 0:
                    if asset == quote_currency:
                        total_value += amount
                    else:
                        # 获取资产价格
                        try:
                            symbol = f"{asset}/{quote_currency}"
                            ticker = await self.fetch_ticker(symbol)
                            asset_value = amount * ticker['last']
                            total_value += asset_value
                        except:
                            # 如果无法获取价格，跳过该资产
                            pass
            
            # 添加理财资产价值
            for asset, amount in self.simulation_funding_balance.items():
                if amount > 0:
                    if asset == quote_currency:
                        total_value += amount
                    else:
                        try:
                            symbol = f"{asset}/{quote_currency}"
                            ticker = await self.fetch_ticker(symbol)
                            asset_value = amount * ticker['last']
                            total_value += asset_value
                        except:
                            pass
            
            return total_value
            
        except Exception as e:
            self.logger.error(f"计算虚拟账户总资产失败: {e}")
            return 0.0

    # === 时间同步等其他必要方法 ===
    
    async def start_periodic_time_sync(self):
        """启动周期性时间同步（虚拟交易中不需要，直接代理）"""
        if hasattr(self.real_exchange, 'start_periodic_time_sync'):
            await self.real_exchange.start_periodic_time_sync()

    async def stop_periodic_time_sync(self):
        """停止周期性时间同步（虚拟交易中不需要，直接代理）"""
        if hasattr(self.real_exchange, 'stop_periodic_time_sync'):
            await self.real_exchange.stop_periodic_time_sync()

    def get_simulation_summary(self):
        """获取虚拟交易总结"""
        try:
            summary = {
                'total_trades': len(self.simulation_trades),
                'current_balances': self.simulation_balances['total'].copy(),
                'funding_balances': self.simulation_funding_balance.copy(),
                'initial_balance': settings.SIMULATION_INITIAL_BALANCE,
                'trades_history': self.simulation_trades[-10:]  # 最近10笔交易
            }
            return summary
        except Exception as e:
            self.logger.error(f"生成虚拟交易总结失败: {e}")
            return {}