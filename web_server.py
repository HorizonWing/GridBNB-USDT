import os
import json
from aiohttp import web
import logging
from datetime import datetime
import psutil
import config
import aiofiles
from helpers import LogConfig

class IPLogger:
    def __init__(self):
        self.ip_records = []  # 存储IP访问记录
        self.max_records = 100  # 最多保存100条记录
        self._log_cache = {'content': None, 'timestamp': 0}  # 添加日志缓存
        self._cache_ttl = 2  # 缓存有效期（秒）

    def add_record(self, ip, path):
        # 查找是否存在相同IP的记录
        for record in self.ip_records:
            if record['ip'] == ip:
                # 如果找到相同IP，只更新时间
                record['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                record['path'] = path  # 更新访问路径
                return
        
        # 如果是新IP，添加新记录
        record = {
            'ip': ip,
            'path': path,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.ip_records.append(record)
        
        # 如果超出最大记录数，删除最早的记录
        if len(self.ip_records) > self.max_records:
            self.ip_records.pop(0)

    def get_records(self):
        return self.ip_records

def get_system_stats():
    """获取系统资源使用情况"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    memory_used = memory.used / (1024 * 1024 * 1024)  # 转换为GB
    memory_total = memory.total / (1024 * 1024 * 1024)
    return {
        'cpu_percent': cpu_percent,
        'memory_used': round(memory_used, 2),
        'memory_total': round(memory_total, 2),
        'memory_percent': memory.percent
    }

async def _read_log_content():
    """公共的日志读取函数"""
    log_path = os.path.join(LogConfig.LOG_DIR, 'trading_system.log')
    if not os.path.exists(log_path):
        return None
        
    async with aiofiles.open(log_path, mode='r', encoding='utf-8') as f:
        content = await f.read()
        
    # 将日志按行分割并倒序排列
    lines = content.strip().split('\n')
    lines.reverse()
    return '\n'.join(lines)

async def handle_log(request):
    try:
        # 记录IP访问
        ip = request.remote
        request.app['ip_logger'].add_record(ip, request.path)
        
        # 获取系统资源状态
        system_stats = get_system_stats()
        
        # 读取日志内容
        content = await _read_log_content()
        if content is None:
            return web.Response(text="日志文件不存在", status=404)
            
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>网格交易监控系统</title>
            <meta charset="utf-8">
            <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
            <style>
                .grid-container {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 1rem;
                    padding: 1rem;
                }}
                .card {{
                    background: white;
                    border-radius: 0.5rem;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    padding: 1rem;
                }}
                .status-value {{
                    font-size: 1.5rem;
                    font-weight: bold;
                    color: #2563eb;
                }}
                .profit {{ color: #10b981; }}
                .loss {{ color: #ef4444; }}
                .log-container {{
                    height: calc(100vh - 400px);
                    overflow-y: auto;
                    background: #1e1e1e;
                    color: #d4d4d4;
                    padding: 1rem;
                    border-radius: 0.5rem;
                }}
            </style>
        </head>
        <body class="bg-gray-100">
            <div class="container mx-auto px-4 py-8">
                <h1 class="text-3xl font-bold mb-8 text-center text-gray-800">网格交易监控系统</h1>
                
                <!-- 状态卡片 -->
                <div class="grid-container mb-8">
                    <div class="card">
                        <h2 class="text-lg font-semibold mb-4">基本信息 & S1</h2>
                        <div class="space-y-2">
                            <div class="flex justify-between">
                                <span>交易对</span>
                                <span class="status-value">{request.app['trader'].symbol}</span>
                            </div>
                            <div class="flex justify-between">
                                <span>基准价格</span>
                                <span class="status-value" id="base-price">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>当前价格 (USDT)</span>
                                <span class="status-value" id="current-price">--</span>
                            </div>
                            <div class="flex justify-between pt-2 border-t mt-2">
                                <span>52日最高价 (S1)</span>
                                <span class="status-value" id="s1-high">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>52日最低价 (S1)</span>
                                <span class="status-value" id="s1-low">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>当前仓位 (%)</span>
                                <span class="status-value" id="position-percentage">--</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2 class="text-lg font-semibold mb-4">网格参数</h2>
                        <div class="space-y-2">
                            <div class="flex justify-between">
                                <span>网格大小</span>
                                <span class="status-value" id="grid-size">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>触发阈值</span>
                                <span class="status-value" id="threshold">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>目标委托金额</span>
                                <span class="status-value" id="target-order-amount">--</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2 class="text-lg font-semibold mb-4">资金状况</h2>
                        <div class="space-y-2">
                            <div class="flex justify-between">
                                <span>总资产(USDT)</span>
                                <span class="status-value" id="total-assets">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>USDT余额</span>
                                <span class="status-value" id="usdt-balance">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span><span id="symbol-base"></span>余额</span>
                                <span class="status-value" id="bnb-balance">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>总盈亏(USDT)</span>
                                <span class="status-value" id="total-profit">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>盈亏率(%)</span>
                                <span class="status-value" id="profit-rate">--</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 系统资源监控 -->
                <div class="card mb-8">
                    <h2 class="text-lg font-semibold mb-4">系统资源</h2>
                    <div class="grid grid-cols-2 gap-4">
                        <div class="p-4 bg-gray-50 rounded-lg">
                            <div class="text-sm text-gray-600">CPU使用率</div>
                            <div class="text-2xl font-bold mt-1">{system_stats['cpu_percent']}%</div>
                        </div>
                        <div class="p-4 bg-gray-50 rounded-lg">
                            <div class="text-sm text-gray-600">内存使用</div>
                            <div class="text-2xl font-bold mt-1">{system_stats['memory_percent']}%</div>
                            <div class="text-sm text-gray-500">
                                {system_stats['memory_used']}GB / {system_stats['memory_total']}GB
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 趋势分析结果 -->
                <div class="card mb-8">
                    <h2 class="text-lg font-semibold mb-4">趋势分析结果</h2>
                    
                    <!-- 最新趋势信号 -->
                    <div class="mb-6">
                        <h3 class="text-md font-medium mb-3">当前趋势信号</h3>
                        <div class="bg-gray-50 p-4 rounded-lg mb-4">
                            <div class="grid grid-cols-2 gap-x-4 gap-y-2">
                                <div>
                                    <span class="text-gray-600 text-sm">信号类型</span>
                                    <div class="font-bold text-lg" id="trend-signal">--</div>
                                </div>
                                <div>
                                    <span class="text-gray-600 text-sm">市场状态</span>
                                    <div class="font-bold text-lg" id="market-state">--</div>
                                </div>
                                <div>
                                    <span class="text-gray-600 text-sm">建议操作</span>
                                    <div class="font-bold text-lg" id="advice">--</div>
                                </div>
                                <div>
                                    <span class="text-gray-600 text-sm">信号置信度</span>
                                    <div class="font-bold text-lg" id="confidence">--</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 趋势历史记录 -->
                    <div>
                        <h3 class="text-md font-medium mb-3">趋势历史记录</h3>
                        <div class="overflow-x-auto">
                            <table class="min-w-full">
                                <thead>
                                    <tr class="bg-gray-50">
                                        <th class="px-3 py-2 text-left">时间</th>
                                        <th class="px-3 py-2 text-left">信号</th>
                                        <th class="px-3 py-2 text-left">长期趋势</th>
                                        <th class="px-3 py-2 text-left">中期趋势</th>
                                        <th class="px-3 py-2 text-left">短期趋势</th>
                                        <th class="px-3 py-2 text-left">建议</th>
                                        <th class="px-3 py-2 text-left">市场状态</th>
                                    </tr>
                                </thead>
                                <tbody id="trend-history">
                                    <!-- 趋势历史记录将通过JavaScript动态插入 -->
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- 最近交易记录 -->
                <div class="card mt-4 mb-8">
                    <h2 class="text-lg font-semibold mb-4">最近交易</h2>
                    <div class="overflow-x-auto">
                        <table class="min-w-full">
                            <thead>
                                <tr class="border-b">
                                    <th class="text-left py-2">时间</th>
                                    <th class="text-left py-2">方向</th>
                                    <th class="text-left py-2">价格</th>
                                    <th class="text-left py-2">数量</th>
                                    <th class="text-left py-2">金额(USDT)</th>
                                </tr>
                            </thead>
                            <tbody id="trade-history">
                                <!-- 交易记录将通过JavaScript动态插入 -->
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- IP访问记录 -->
                <div class="card mb-8">
                    <h2 class="text-lg font-semibold mb-4">访问记录</h2>
                    <div class="overflow-x-auto">
                        <table class="min-w-full">
                            <thead>
                                <tr class="bg-gray-50">
                                    <th class="px-6 py-3 text-left">时间</th>
                                    <th class="px-6 py-3 text-left">IP地址</th>
                                    <th class="px-6 py-3 text-left">访问路径</th>
                                </tr>
                            </thead>
                            <tbody>
                                {''.join([f'''
                                <tr class="border-b">
                                    <td class="px-6 py-4">{record["time"]}</td>
                                    <td class="px-6 py-4">{record["ip"]}</td>
                                    <td class="px-6 py-4">{record["path"]}</td>
                                </tr>
                                ''' for record in reversed(request.app['ip_logger'].get_records())])}
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- 系统日志 -->
                <div class="card">
                    <h2 class="text-lg font-semibold mb-4">系统日志</h2>
                    <div class="log-container" id="log-content">
                        <pre>{content}</pre>
                    </div>
                </div>
            </div>

            <script>
                async function updateStatus() {{
                    try {{
                        const response = await fetch('/api/status');
                        const data = await response.json();
                        
                        if (data.error) {{
                            console.error('获取状态失败:', data.error);
                            return;
                        }}
                        
                        // 更新基本信息
                        document.querySelector('#base-price').textContent = 
                            data.base_price ? data.base_price.toFixed(2) + ' USDT' : '--';
                        
                        // 更新当前价格
                        document.querySelector('#current-price').textContent = 
                            data.current_price ? data.current_price.toFixed(2) : '--';
                        
                        // 更新 S1 信息和仓位
                        document.querySelector('#s1-high').textContent = 
                            data.s1_daily_high ? data.s1_daily_high.toFixed(2) : '--';
                        document.querySelector('#s1-low').textContent = 
                            data.s1_daily_low ? data.s1_daily_low.toFixed(2) : '--';
                        document.querySelector('#position-percentage').textContent = 
                            data.position_percentage != null ? data.position_percentage.toFixed(2) + '%' : '--';
                        
                        // 更新网格参数
                        document.querySelector('#grid-size').textContent = 
                            data.grid_size ? (data.grid_size * 100).toFixed(2) + '%' : '--';
                        document.querySelector('#threshold').textContent = 
                            data.threshold ? (data.threshold * 100).toFixed(2) + '%' : '--';
                        
                        // 更新资金状况
                        document.querySelector('#total-assets').textContent = 
                            data.total_assets ? data.total_assets.toFixed(2) + ' USDT' : '--';
                        document.querySelector('#usdt-balance').textContent = 
                            data.usdt_balance != null ? data.usdt_balance.toFixed(2) : '--';
                        document.querySelector('#bnb-balance').textContent = 
                            data.bnb_balance != null ? data.bnb_balance.toFixed(4) : '--';
                        document.querySelector('#symbol-base').textContent = 
                            data.symbol_base != null ? data.symbol_base : '--';
                        
                        // 更新盈亏信息
                        const totalProfitElement = document.querySelector('#total-profit');
                        totalProfitElement.textContent = data.total_profit ? data.total_profit.toFixed(2) : '--';
                        totalProfitElement.className = `status-value ${{data.total_profit >= 0 ? 'profit' : 'loss'}}`;

                        const profitRateElement = document.querySelector('#profit-rate');
                        profitRateElement.textContent = data.profit_rate ? data.profit_rate.toFixed(2) + '%' : '--';
                        profitRateElement.className = `status-value ${{data.profit_rate >= 0 ? 'profit' : 'loss'}}`;
                        
                        // 更新交易历史
                        document.querySelector('#trade-history').innerHTML = data.trade_history.map(function(trade) {{ return ` 
                            <tr class="border-b">
                                <td class="py-2">${{trade.timestamp}}</td>
                                <td class="py-2 ${{trade.side === 'buy' ? 'text-green-500' : 'text-red-500'}}">
                                    ${{trade.side === 'buy' ? '买入' : '卖出'}}
                                </td>
                                <td class="py-2">${{parseFloat(trade.price).toFixed(2)}}</td>
                                <td class="py-2">${{parseFloat(trade.amount).toFixed(4)}}</td>
                                <td class="py-2">${{(parseFloat(trade.price) * parseFloat(trade.amount)).toFixed(2)}}</td>
                            </tr>
                        `; }}).join('');
                        
                        // 更新目标委托金额
                        document.querySelector('#target-order-amount').textContent = 
                            data.target_order_amount ? data.target_order_amount.toFixed(2) + ' USDT' : '--';
                        
                        // 更新趋势信号
                        if (data.trend_data && data.trend_data.latest) {{
                            const trend = data.trend_data.latest;
                            document.querySelector('#trend-signal').textContent = trend.signal || '--';
                            document.querySelector('#market-state').textContent = trend.market_state || '--';
                            document.querySelector('#advice').textContent = trend.advice || '--';
                            document.querySelector('#confidence').textContent = trend.confidence || '--';
                        }}
                        
                        // 更新趋势历史记录
                        if (data.trend_data && data.trend_data.history && data.trend_data.history.length > 0) {{
                            document.querySelector('#trend-history').innerHTML = data.trend_data.history.map(function(trend) {{ return ` 
                                <tr class="border-b">
                                    <td class="px-3 py-2">${{trend.timestamp || '--'}}</td>
                                    <td class="px-3 py-2">${{trend.signal || '--'}}</td>
                                    <td class="px-3 py-2">${{trend.long_trend || '--'}}</td>
                                    <td class="px-3 py-2">${{trend.mid_trend || '--'}}</td>
                                    <td class="px-3 py-2">${{trend.short_trend || '--'}}</td>
                                    <td class="px-3 py-2">${{trend.advice || '--'}}</td>
                                    <td class="px-3 py-2">${{trend.market_state || '--'}}</td>
                                </tr>
                            `; }}).join('');
                        }}
                        
                        console.log('状态更新成功:', data);
                    }} catch (error) {{
                        console.error('更新状态失败:', error);
                    }}
                }}

                // 每2秒更新一次状态
                setInterval(updateStatus, 2000);
                
                // 页面加载时立即更新一次
                updateStatus();
            </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        return web.Response(text=f"Error: {str(e)}", status=500)

async def handle_status(request):
    """处理状态API请求"""
    try:
        trader = request.app['trader']
        s1_controller = trader.position_controller_s1 # 获取 S1 控制器实例

        # 获取交易所数据
        balance = await trader.exchange.fetch_balance()
        current_price = await trader._get_latest_price() or 0 # 提供默认值以防失败
        
        # 获取理财账户余额
        funding_balance = await trader.exchange.fetch_funding_balance()
        
        # 获取网格参数
        grid_size = trader.grid_size
        grid_size_decimal = grid_size / 100 if grid_size else 0
        threshold = grid_size_decimal / 5
        
        # 计算总资产
        SYMBOL = config.SYMBOL if config.SYMBOL else 'BNB/USDT'
        SYMBOL_BASE = SYMBOL.split('/')[0] if '/' in SYMBOL else 'BNB'
        SYMBOL_QUOTE = SYMBOL.split('/')[1] if '/' in SYMBOL else 'USDT'
        bnb_balance = float(balance['total'].get(SYMBOL_BASE, 0))
        usdt_balance = float(balance['total'].get(SYMBOL_QUOTE, 0))
        total_assets = usdt_balance + (bnb_balance * current_price)
        
        # 计算总盈亏和盈亏率
        initial_principal = trader.config.INITIAL_PRINCIPAL
        total_profit = 0.0
        profit_rate = 0.0
        if initial_principal > 0:
            total_profit = total_assets - initial_principal
            profit_rate = (total_profit / initial_principal) * 100
        else:
            logging.warning("初始本金未设置或为0，无法计算盈亏率")
        
        # 获取最近交易信息
        last_trade_price = trader.last_trade_price
        last_trade_time = trader.last_trade_time
        last_trade_time_str = datetime.fromtimestamp(last_trade_time).strftime('%Y-%m-%d %H:%M:%S') if last_trade_time else '--'
        
        # 获取交易历史
        trade_history = []
        if hasattr(trader, 'order_tracker'):
            trades = trader.order_tracker.get_trade_history()
            trade_history = [{
                'timestamp': datetime.fromtimestamp(trade['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                'side': trade.get('side', '--'),
                'price': trade.get('price', 0),
                'amount': trade.get('amount', 0),
                'profit': trade.get('profit', 0)
            } for trade in trades[-10:]]  # 只取最近10笔交易
        
        # 计算目标委托金额 (总资产的10%)
        target_order_amount = await trader._calculate_order_amount('buy') # buy/sell 结果一样
        
        # 获取仓位百分比 - 使用风控管理器的方法获取最准确的仓位比例
        position_ratio = await trader.risk_manager._get_position_ratio()
        position_percentage = position_ratio * 100
        
        # 获取 S1 高低价
        s1_high = s1_controller.s1_daily_high if s1_controller else None
        s1_low = s1_controller.s1_daily_low if s1_controller else None
        
        # 获取趋势分析数据
        trend_data = await get_trend_analysis_data(symbol=SYMBOL, limit=10)

        # 构建响应数据
        status = {
            "base_price": trader.base_price,
            "current_price": current_price,
            "grid_size": grid_size_decimal,
            "threshold": threshold,
            "total_assets": total_assets,
            "usdt_balance": usdt_balance,
            "bnb_balance": bnb_balance,
            "target_order_amount": target_order_amount,
            "trade_history": trade_history or [],
            "last_trade_price": last_trade_price,
            "last_trade_time": last_trade_time,
            "last_trade_time_str": last_trade_time_str,
            "total_profit": total_profit,
            "profit_rate": profit_rate,
            "s1_daily_high": s1_high,
            "s1_daily_low": s1_low,
            "position_percentage": position_percentage,
            "symbol_base": SYMBOL_BASE,
            "symbol_quote": SYMBOL_QUOTE,
            "trend_data": trend_data  # 添加趋势分析数据
        }
        
        return web.json_response(status)
    except Exception as e:
        logging.error(f"获取状态数据失败: {str(e)}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

async def handle_trend_analysis(request):
    """处理趋势分析API请求"""
    try:
        symbol = request.query.get('symbol', config.SYMBOL)
        limit = int(request.query.get('limit', 10))
        trend_data = await get_trend_analysis_data(symbol=symbol, limit=limit)
        return web.json_response(trend_data)
    except Exception as e:
        logging.error(f"获取趋势分析数据失败: {str(e)}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

async def start_web_server(trader):
    app = web.Application()
    # 添加中间件处理无效请求
    @web.middleware
    async def error_middleware(request, handler):
        try:
            return await handler(request)
        except web.HTTPException as ex:
            return web.json_response(
                {"error": str(ex)},
                status=ex.status,
                headers={'Access-Control-Allow-Origin': '*'}
            )
        except Exception as e:
            return web.json_response(
                {"error": "Internal Server Error"},
                status=500,
                headers={'Access-Control-Allow-Origin': '*'}
            )
    
    app.middlewares.append(error_middleware)
    app['trader'] = trader
    app['ip_logger'] = IPLogger()
    
    # 禁用访问日志
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    
    app.router.add_get('/', handle_log)
    app.router.add_get('/api/logs', handle_log_content)
    app.router.add_get('/api/status', handle_status)
    app.router.add_get('/api/trend', handle_trend_analysis)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 58181)
    await site.start()

    # 打印访问地址
    local_ip = "localhost"  # 或者使用实际IP
    logging.info(f"Web服务已启动:")
    logging.info(f"- 本地访问: http://{local_ip}:58181")
    logging.info(f"- 局域网访问: http://0.0.0.0:58181")

async def handle_log_content(request):
    """只返回日志内容的API端点"""
    try:
        content = await _read_log_content()
        if content is None:
            return web.Response(text="", status=404)
            
        return web.Response(text=content)
    except Exception as e:
        return web.Response(text="", status=500)

# 添加趋势分析结果读取函数
async def get_trend_analysis_data(symbol='BTC/USDT', limit=10):
    """读取趋势分析数据
    
    Args:
        symbol: 交易对，如 'BTC/USDT'
        limit: 最多返回的历史记录数量
        
    Returns:
        dict: 包含最新信号和历史信号的字典
    """
    try:
        # 准备文件路径
        symbol_safe = symbol.replace('/', '_')
        signal_file = f"{config.TREND_OUTPUT_DIR}/{symbol_safe}_signal.json"
        history_file = f"{config.TREND_OUTPUT_DIR}/{symbol_safe}_signal_history.json"
        
        # 获取最新信号
        latest_signal = None
        if os.path.exists(signal_file):
            with open(signal_file, 'r', encoding='utf-8') as f:
                latest_signal = json.load(f)
        
        # 获取历史信号
        history = []
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                # 只返回指定数量的最新记录
                history = history[-limit:] if limit > 0 else history
        
        return {
            'latest': latest_signal,
            'history': history
        }
    except Exception as e:
        logging.error(f"读取趋势分析数据失败: {str(e)}", exc_info=True)
        return {'latest': None, 'history': []} 