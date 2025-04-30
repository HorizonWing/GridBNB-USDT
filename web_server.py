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
            
        # 使用普通字符串而不是f-string
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>网格交易监控系统</title>
            <meta charset="utf-8">
            <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
            <style>
                .grid-container {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 1rem;
                    padding: 1rem;
                }
                .card {
                    background: white;
                    border-radius: 0.5rem;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    padding: 1rem;
                }
                .status-value {
                    font-size: 1.5rem;
                    font-weight: bold;
                    color: #2563eb;
                }
                .profit { color: #10b981; }
                .loss { color: #ef4444; }
                .log-container {
                    height: calc(100vh - 400px);
                    overflow-y: auto;
                    background: #1e1e1e;
                    color: #d4d4d4;
                    padding: 1rem;
                    border-radius: 0.5rem;
                }
                /* 趋势颜色样式 */
                .trend-up { color: #10b981; font-weight: bold; }
                .trend-down { color: #ef4444; font-weight: bold; }
                .trend-sideways { color: #6b7280; font-weight: bold; }
                .signal-buy { background-color: rgba(16, 185, 129, 0.1); }
                .signal-sell { background-color: rgba(239, 68, 68, 0.1); }
                .signal-hold { background-color: rgba(107, 114, 128, 0.15); }
                .confidence-high { color: #10b981; font-weight: bold; }
                .confidence-medium { color: #f59e0b; font-weight: bold; }
                .confidence-low { color: #6b7280; font-weight: bold; }
                
                /* 信号样式增强 */
                #trend-signal.trend-up, 
                #trend-signal.trend-down { 
                    font-size: 1.75rem; 
                    text-shadow: 0 1px 2px rgba(0,0,0,0.1);
                }
                .signal-buy.border-l-4, 
                .signal-sell.border-l-4 {
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }
                
                /* 表格样式增强 */
                #trend-history tr:hover {
                    background-color: rgba(243, 244, 246, 0.7);
                }
                #trend-history td {
                    padding-top: 8px;
                    padding-bottom: 8px;
                    border-bottom: 1px solid #e5e7eb;
                }
            </style>
        </head>
        <body class="bg-gray-100">
            <div class="container mx-auto px-4 py-8">
        """
        
        # 添加标题部分
        html += f"""
                <h1 class="text-3xl font-bold mb-8 text-center text-gray-800">网格交易监控系统</h1>
                
                <!-- 交易系统状态信息 -->
                <div class="card mb-4">
                    <h2 class="text-lg font-semibold mb-4">系统状态</h2>
                    <div class="grid grid-cols-2 gap-4">
                        <div class="p-4 bg-gray-50 rounded-lg">
                            <div class="text-sm text-gray-600">交易系统类型</div>
                            <div class="text-xl font-bold mt-1" id="trader-type">--</div>
                        </div>
                        <div class="p-4 bg-gray-50 rounded-lg">
                            <div class="text-sm text-gray-600">交易功能</div>
                            <div class="text-xl font-bold mt-1" id="trading-status">--</div>
                        </div>
                    </div>
                </div>
                
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
                                <span>当前价格</span>
                                <span class="status-value" id="current-price">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>S1日内高点</span>
                                <span class="status-value" id="s1-high">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>S1日内低点</span>
                                <span class="status-value" id="s1-low">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>当前仓位</span>
                                <span class="status-value" id="position-percentage">--</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 新增网格信息 -->
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
                            <div class="flex justify-between">
                                <span>最近交易价格</span>
                                <span class="status-value" id="last-trade-price">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>最近交易时间</span>
                                <span class="status-value" id="last-trade-time">--</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 新增趋势交易信息 -->
                    <div class="card">
                        <h2 class="text-lg font-semibold mb-4">趋势参数</h2>
                        <div class="space-y-2">
                            <div class="flex justify-between">
                                <span>当前ATR</span>
                                <span class="status-value" id="atr-value">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>每笔风险</span>
                                <span class="status-value" id="risk-per-trade">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>止损ATR乘数</span>
                                <span class="status-value" id="sl-atr-multiplier">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>止盈ATR乘数</span>
                                <span class="status-value" id="tp-atr-multiplier">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>是否震荡市场</span>
                                <span class="status-value" id="is-consolidating">--</span>
                            </div>
                            
                            <div class="mt-4 mb-2 pt-2 border-t border-gray-200">
                                <h3 class="text-md font-semibold">开仓状态</h3>
                            </div>
                            
                            <div class="flex justify-between">
                                <span>开仓信号</span>
                                <span class="status-value" id="entry-signal">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>开仓条件</span>
                                <span class="status-value" id="can-open-position">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>挂单状态</span>
                                <span class="status-value" id="order-status">--</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 新增合约持仓信息 -->
                    <div class="card">
                        <h2 class="text-lg font-semibold mb-4">合约持仓</h2>
                        <div class="space-y-2">
                            <div class="flex justify-between">
                                <span>持仓方向</span>
                                <span class="status-value" id="position-side">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>持仓大小</span>
                                <span class="status-value" id="position-size">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>杠杆倍数</span>
                                <span class="status-value" id="leverage">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>入场价格</span>
                                <span class="status-value" id="entry-price">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>当前价格</span>
                                <span class="status-value" id="contract-current-price">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>价格变动</span>
                                <span class="status-value" id="price-change">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>止损价格</span>
                                <span class="status-value" id="stop-loss">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>止盈价格</span>
                                <span class="status-value" id="take-profit">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>未实现盈亏</span>
                                <span class="status-value" id="unrealized-pnl">--</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 资产和盈亏信息 -->
                    <div class="card">
                        <h2 class="text-lg font-semibold mb-4">资产和盈亏</h2>
                        <div class="space-y-2">
                            <div class="flex justify-between">
                                <span>USDT余额</span>
                                <span class="status-value" id="usdt-balance">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>代币余额</span>
                                <span class="status-value" id="token-balance">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>总资产</span>
                                <span class="status-value" id="total-assets">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>总盈亏</span>
                                <span class="status-value" id="total-profit">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span>盈亏率</span>
                                <span class="status-value" id="profit-rate">--</span>
                            </div>
                        </div>
                    </div>
                </div>
        """
        
        # 添加系统资源监控部分
        html += f"""
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
        """
        
        # 添加IP访问记录部分
        html += f"""
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
                                {''.join(['<tr class="border-b"><td class="px-6 py-4">' + record['time'] + '</td><td class="px-6 py-4">' + record['ip'] + '</td><td class="px-6 py-4">' + record['path'] + '</td></tr>' for record in reversed(request.app['ip_logger'].get_records())])}
                            </tbody>
                        </table>
                    </div>
                </div>
                
                <!-- 趋势分析结果 -->
                <div class="card mb-8">
                    <h2 class="text-lg font-semibold mb-4">趋势分析结果</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                        <div class="p-4 bg-gray-50 rounded-lg">
                            <div class="text-sm text-gray-600">最新趋势</div>
                            <div class="text-2xl font-bold mt-1" id="trend-direction">--</div>
                        </div>
                        <div class="p-4 bg-gray-50 rounded-lg">
                            <div class="text-sm text-gray-600">最新信号</div>
                            <div class="text-2xl font-bold mt-1" id="trend-signal">--</div>
                        </div>
                        <div class="p-4 bg-gray-50 rounded-lg">
                            <div class="text-sm text-gray-600">信号置信度</div>
                            <div class="text-2xl font-bold mt-1" id="trend-confidence">--</div>
                        </div>
                        <div class="p-4 bg-gray-50 rounded-lg">
                            <div class="text-sm text-gray-600">分析时间</div>
                            <div class="text-xl font-bold mt-1" id="trend-time">--</div>
                        </div>
                    </div>
                    
                    <div class="mt-6">
                        <h3 class="text-md font-semibold mb-2">历史趋势记录</h3>
                        <div class="overflow-x-auto">
                            <table class="min-w-full">
                                <thead>
                                    <tr class="bg-gray-50">
                                        <th class="px-3 py-2 text-left">时间</th>
                                        <th class="px-3 py-2 text-left">趋势</th>
                                        <th class="px-3 py-2 text-left">信号</th>
                                        <th class="px-3 py-2 text-left">价格</th>
                                        <th class="px-3 py-2 text-left">置信度</th>
                                    </tr>
                                </thead>
                                <tbody id="trend-history">
                                    <!-- 趋势历史记录会通过JavaScript添加 -->
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
        
        """
        
        # 添加系统日志部分
        html += f"""
                <!-- 系统日志 -->
                <div class="card">
                    <h2 class="text-lg font-semibold mb-4">系统日志</h2>
                    <div class="log-container" id="log-content">
                        <pre>{content}</pre>
                    </div>
                </div>
            </div>
        """
        
        # 添加JavaScript部分，使用普通字符串
        html += """
            <script>
                async function updateStatus() {
                    try {
                        const response = await fetch('/api/status');
                        const data = await response.json();
                        
                        if (data.error) {
                            console.error('获取状态失败:', data.error);
                            return;
                        }
                        
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
                        
                        // 更新交易系统状态
                        const traderTypeElement = document.querySelector('#trader-type');
                        if (data.is_trend_trader) {
                            traderTypeElement.textContent = '趋势交易系统';
                            traderTypeElement.className = 'text-xl font-bold mt-1 text-blue-600';
                        } else {
                            traderTypeElement.textContent = '网格交易系统';
                            traderTypeElement.className = 'text-xl font-bold mt-1 text-green-600';
                        }
                        
                        // 更新交易功能状态
                        const tradingStatusElement = document.querySelector('#trading-status');
                        if (data.trading_enabled) {
                            tradingStatusElement.textContent = '已启用';
                            tradingStatusElement.className = 'text-xl font-bold mt-1 text-green-600';
                        } else {
                            tradingStatusElement.textContent = '已禁用（仅监控模式）';
                            tradingStatusElement.className = 'text-xl font-bold mt-1 text-red-600';
                        }
                        
                        // 更新网格参数
                        document.querySelector('#grid-size').textContent = 
                            data.grid_size != null ? (data.grid_size * 100).toFixed(2) + '%' : '--';
                        document.querySelector('#threshold').textContent = 
                            data.threshold != null ? (data.threshold * 100).toFixed(2) + '%' : '--';
                        document.querySelector('#target-order-amount').textContent = 
                            data.target_order_amount ? data.target_order_amount.toFixed(4) + ' ' + data.symbol_base : '--';
                        document.querySelector('#last-trade-price').textContent = 
                            data.last_trade_price ? data.last_trade_price.toFixed(2) + ' USDT' : '--';
                        document.querySelector('#last-trade-time').textContent = 
                            data.last_trade_time_str || '--';
                            
                        // 更新趋势参数
                        document.querySelector('#atr-value').textContent = 
                            data.atr != null ? data.atr.toFixed(2) : '--';
                        document.querySelector('#risk-per-trade').textContent = 
                            data.risk_per_trade != null ? data.risk_per_trade.toFixed(2) + '%' : '--';
                        document.querySelector('#sl-atr-multiplier').textContent = 
                            data.sl_atr_multiplier != null ? data.sl_atr_multiplier.toFixed(2) : '--';
                        document.querySelector('#tp-atr-multiplier').textContent = 
                            data.tp_atr_multiplier != null ? data.tp_atr_multiplier.toFixed(2) : '--';
                        document.querySelector('#is-consolidating').textContent = 
                            data.is_consolidating != null ? (data.is_consolidating ? '是' : '否') : '--';
                            
                        // 更新开仓信号和条件
                        const entrySignalElement = document.querySelector('#entry-signal');
                        if (data.entry_signal) {
                            entrySignalElement.textContent = data.entry_signal === 'long' ? '做多' : 
                                data.entry_signal === 'short' ? '做空' : '无信号';
                                
                            entrySignalElement.className = data.entry_signal === 'long' ? 'status-value trend-up' : 
                                data.entry_signal === 'short' ? 'status-value trend-down' : 'status-value';
                        } else {
                            entrySignalElement.textContent = '无信号';
                            entrySignalElement.className = 'status-value';
                        }
                        
                        // 更新开仓条件
                        const canOpenElement = document.querySelector('#can-open-position');
                        if (data.can_open_position != null) {
                            canOpenElement.textContent = data.can_open_position ? '满足' : '不满足';
                            canOpenElement.className = data.can_open_position ? 'status-value trend-up' : 'status-value trend-down';
                        } else {
                            canOpenElement.textContent = '--';
                            canOpenElement.className = 'status-value';
                        }
                        
                        // 更新挂单状态
                        const orderStatusElement = document.querySelector('#order-status');
                        if (data.order_status) {
                            orderStatusElement.textContent = data.order_status;
                            
                            if (data.order_status.includes('正在开仓')) {
                                orderStatusElement.className = 'status-value trend-up';
                            } else if (data.order_status.includes('正在平仓')) {
                                orderStatusElement.className = 'status-value trend-down';
                            } else if (data.order_status.includes('有')) {
                                orderStatusElement.className = 'status-value confidence-medium';
                            } else {
                                orderStatusElement.className = 'status-value';
                            }
                        } else {
                            orderStatusElement.textContent = '--';
                            orderStatusElement.className = 'status-value';
                        }
                        
                        // 更新合约持仓信息
                        if (data.contract_position) {
                            const position = data.contract_position;
                            document.querySelector('#position-side').textContent = 
                                position.side === 'long' ? '多' : position.side === 'short' ? '空' : '--';
                            document.querySelector('#position-size').textContent = 
                                position.size ? position.size.toFixed(4) + ' ' + data.symbol_base : '--';
                            document.querySelector('#leverage').textContent = 
                                position.leverage ? position.leverage + 'x' : '--';
                            document.querySelector('#entry-price').textContent = 
                                position.entry_price ? position.entry_price.toFixed(2) + ' USDT' : '--';
                                
                            // 更新当前价格和价格变动
                            document.querySelector('#contract-current-price').textContent = 
                                data.current_price ? data.current_price.toFixed(2) + ' USDT' : '--';
                                
                            // 计算并显示价格变动
                            if (data.current_price && position.entry_price) {
                                const priceChange = data.current_price - position.entry_price;
                                const priceChangePercent = (priceChange / position.entry_price) * 100;
                                
                                const priceChangeElement = document.querySelector('#price-change');
                                const changeText = priceChangePercent.toFixed(2) + '% (' + 
                                    (priceChange >= 0 ? '+' : '') + priceChange.toFixed(2) + ' USDT)';
                                    
                                priceChangeElement.textContent = changeText;
                                
                                // 设置价格变动颜色（上涨绿色，下跌红色）
                                if (position.side === 'long') {
                                    priceChangeElement.className = priceChange >= 0 ? 'status-value profit' : 'status-value loss';
                                } else {
                                    // 对于空仓，价格下跌是盈利
                                    priceChangeElement.className = priceChange <= 0 ? 'status-value profit' : 'status-value loss';
                                }
                            } else {
                                document.querySelector('#price-change').textContent = '--';
                                document.querySelector('#price-change').className = 'status-value';
                            }
                            
                            document.querySelector('#stop-loss').textContent = 
                                position.stop_loss ? position.stop_loss.toFixed(2) + ' USDT' : '--';
                            document.querySelector('#take-profit').textContent = 
                                position.take_profit ? position.take_profit.toFixed(2) + ' USDT' : '--';
                            
                            // 设置未实现盈亏颜色
                            const pnlElement = document.querySelector('#unrealized-pnl');
                            if (position.unrealized_pnl != null) {
                                pnlElement.textContent = position.unrealized_pnl.toFixed(2) + ' USDT';
                                if (position.unrealized_pnl > 0) {
                                    pnlElement.className = 'status-value profit';
                                } else if (position.unrealized_pnl < 0) {
                                    pnlElement.className = 'status-value loss';
                                } else {
                                    pnlElement.className = 'status-value';
                                }
                            } else {
                                pnlElement.textContent = '--';
                                pnlElement.className = 'status-value';
                            }
                        } else {
                            document.querySelector('#position-side').textContent = '--';
                            document.querySelector('#position-size').textContent = '--';
                            document.querySelector('#leverage').textContent = '--';
                            document.querySelector('#entry-price').textContent = '--';
                            document.querySelector('#contract-current-price').textContent = 
                                data.current_price ? data.current_price.toFixed(2) + ' USDT' : '--';
                            document.querySelector('#price-change').textContent = '--';
                            document.querySelector('#price-change').className = 'status-value';
                            document.querySelector('#stop-loss').textContent = '--';
                            document.querySelector('#take-profit').textContent = '--';
                            document.querySelector('#unrealized-pnl').textContent = '--';
                            document.querySelector('#unrealized-pnl').className = 'status-value';
                        }
                        
                        // 更新资产和盈亏信息
                        document.querySelector('#usdt-balance').textContent = 
                            data.usdt_balance != null ? data.usdt_balance.toFixed(2) + ' ' + data.symbol_quote : '--';
                        document.querySelector('#token-balance').textContent = 
                            data.bnb_balance != null ? data.bnb_balance.toFixed(4) + ' ' + data.symbol_base : '--';
                        document.querySelector('#total-assets').textContent = 
                            data.total_assets != null ? data.total_assets.toFixed(2) + ' ' + data.symbol_quote : '--';
                            
                        // 设置盈亏颜色
                        const totalProfitElement = document.querySelector('#total-profit');
                        if (data.total_profit != null) {
                            totalProfitElement.textContent = data.total_profit.toFixed(2) + ' ' + data.symbol_quote;
                            if (data.total_profit > 0) {
                                totalProfitElement.className = 'status-value profit';
                            } else if (data.total_profit < 0) {
                                totalProfitElement.className = 'status-value loss';
                            } else {
                                totalProfitElement.className = 'status-value';
                            }
                        } else {
                            totalProfitElement.textContent = '--';
                            totalProfitElement.className = 'status-value';
                        }
                        
                        const profitRateElement = document.querySelector('#profit-rate');
                        if (data.profit_rate != null) {
                            profitRateElement.textContent = data.profit_rate.toFixed(2) + '%';
                            if (data.profit_rate > 0) {
                                profitRateElement.className = 'status-value profit';
                            } else if (data.profit_rate < 0) {
                                profitRateElement.className = 'status-value loss';
                            } else {
                                profitRateElement.className = 'status-value';
                            }
                        } else {
                            profitRateElement.textContent = '--';
                            profitRateElement.className = 'status-value';
                        }
                        
                        // 更新趋势分析结果
                        if (data.trend_data && data.trend_data.latest) {
                            const latest = data.trend_data.latest;
                            
                            // 设置趋势方向及样式
                            const directionElement = document.querySelector('#trend-direction');
                            if (latest.trend) {
                                directionElement.textContent = latest.trend === 'up' ? '上升趋势' : 
                                    latest.trend === 'down' ? '下降趋势' : '横盘震荡';
                                
                                directionElement.className = latest.trend === 'up' ? 'text-2xl font-bold mt-1 trend-up' : 
                                    latest.trend === 'down' ? 'text-2xl font-bold mt-1 trend-down' : 
                                    'text-2xl font-bold mt-1 trend-sideways';
                            } else {
                                directionElement.textContent = '--';
                                directionElement.className = 'text-2xl font-bold mt-1';
                            }
                            
                            // 设置信号及样式
                            const signalElement = document.querySelector('#trend-signal');
                            if (latest.signal) {
                                signalElement.textContent = latest.signal === 'buy' ? '买入信号' : 
                                    latest.signal === 'sell' ? '卖出信号' : '持仓观望';
                                
                                signalElement.className = latest.signal === 'buy' ? 'text-2xl font-bold mt-1 trend-up' : 
                                    latest.signal === 'sell' ? 'text-2xl font-bold mt-1 trend-down' : 
                                    'text-2xl font-bold mt-1 trend-sideways';
                            } else {
                                signalElement.textContent = '--';
                                signalElement.className = 'text-2xl font-bold mt-1';
                            }
                            
                            // 设置置信度及样式
                            const confidenceElement = document.querySelector('#trend-confidence');
                            if (latest.confidence) {
                                confidenceElement.textContent = latest.confidence === 'high' ? '高' : 
                                    latest.confidence === 'medium' ? '中' : '低';
                                
                                confidenceElement.className = latest.confidence === 'high' ? 'text-2xl font-bold mt-1 confidence-high' : 
                                    latest.confidence === 'medium' ? 'text-2xl font-bold mt-1 confidence-medium' : 
                                    'text-2xl font-bold mt-1 confidence-low';
                            } else {
                                confidenceElement.textContent = '--';
                                confidenceElement.className = 'text-2xl font-bold mt-1';
                            }
                            
                            // 设置分析时间
                            document.querySelector('#trend-time').textContent = 
                                latest.timestamp ? latest.timestamp : '--';
                            
                            // 更新历史趋势记录
                            if (data.trend_data.history && data.trend_data.history.length > 0) {
                                const historyTableBody = document.querySelector('#trend-history');
                                historyTableBody.innerHTML = ''; // 清空表格
                                
                                data.trend_data.history.forEach(record => {
                                    // 创建行并设置适当的类
                                    const row = document.createElement('tr');
                                    row.className = record.signal === 'buy' ? 'signal-buy' : 
                                        record.signal === 'sell' ? 'signal-sell' : 'signal-hold';
                                    
                                    // 添加时间列
                                    const timeCell = document.createElement('td');
                                    timeCell.className = 'px-3 py-2';
                                    timeCell.textContent = record.timestamp || '--';
                                    row.appendChild(timeCell);
                                    
                                    // 添加趋势列
                                    const trendCell = document.createElement('td');
                                    trendCell.className = 'px-3 py-2';
                                    if (record.trend) {
                                        const trendSpan = document.createElement('span');
                                        trendSpan.textContent = record.trend === 'up' ? '上升' : 
                                            record.trend === 'down' ? '下降' : '横盘';
                                        trendSpan.className = record.trend === 'up' ? 'trend-up' : 
                                            record.trend === 'down' ? 'trend-down' : 'trend-sideways';
                                        trendCell.appendChild(trendSpan);
                                    } else {
                                        trendCell.textContent = '--';
                                    }
                                    row.appendChild(trendCell);
                                    
                                    // 添加信号列
                                    const signalCell = document.createElement('td');
                                    signalCell.className = 'px-3 py-2';
                                    if (record.signal) {
                                        const signalSpan = document.createElement('span');
                                        signalSpan.textContent = record.signal === 'buy' ? '买入' : 
                                            record.signal === 'sell' ? '卖出' : '观望';
                                        signalSpan.className = record.signal === 'buy' ? 'trend-up' : 
                                            record.signal === 'sell' ? 'trend-down' : 'trend-sideways';
                                        signalCell.appendChild(signalSpan);
                                    } else {
                                        signalCell.textContent = '--';
                                    }
                                    row.appendChild(signalCell);
                                    
                                    // 添加价格列
                                    const priceCell = document.createElement('td');
                                    priceCell.className = 'px-3 py-2';
                                    priceCell.textContent = record.price ? record.price.toFixed(2) : '--';
                                    row.appendChild(priceCell);
                                    
                                    // 添加置信度列
                                    const confidenceCell = document.createElement('td');
                                    confidenceCell.className = 'px-3 py-2';
                                    if (record.confidence) {
                                        const confSpan = document.createElement('span');
                                        confSpan.textContent = record.confidence === 'high' ? '高' : 
                                            record.confidence === 'medium' ? '中' : '低';
                                        confSpan.className = record.confidence === 'high' ? 'confidence-high' : 
                                            record.confidence === 'medium' ? 'confidence-medium' : 'confidence-low';
                                        confidenceCell.appendChild(confSpan);
                                    } else {
                                        confidenceCell.textContent = '--';
                                    }
                                    row.appendChild(confidenceCell);
                                    
                                    // 将行添加到表格
                                    historyTableBody.appendChild(row);
                                });
                            }
                        } else {
                            // 如果没有趋势数据，设置默认值
                            document.querySelector('#trend-direction').textContent = '--';
                            document.querySelector('#trend-direction').className = 'text-2xl font-bold mt-1';
                            document.querySelector('#trend-signal').textContent = '--';
                            document.querySelector('#trend-signal').className = 'text-2xl font-bold mt-1';
                            document.querySelector('#trend-confidence').textContent = '--';
                            document.querySelector('#trend-confidence').className = 'text-2xl font-bold mt-1';
                            document.querySelector('#trend-time').textContent = '--';
                            document.querySelector('#trend-history').innerHTML = '';
                        }
                        
                    } catch (error) {
                        console.error('更新状态失败:', error);
                    }
                }

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
        s1_controller = getattr(trader, 'position_controller_s1', None)  # 获取 S1 控制器实例,不存在则为None
        is_trend_trader = hasattr(trader, 'current_position') and hasattr(trader, 'current_atr')

        # 获取交易所数据
        balance = await trader.exchange.fetch_balance()
        
        # 获取最新价格 - 添加更强大的错误处理
        current_price = 0
        try:
            if hasattr(trader, '_get_latest_price') and callable(trader._get_latest_price):
                current_price = await trader._get_latest_price() or 0
            else:
                # 备用方案：直接从交易所获取价格
                ticker = await trader.exchange.fetch_ticker(trader.symbol)
                current_price = ticker['last'] if ticker and 'last' in ticker else 0
        except Exception as e:
            logging.error(f"获取最新价格失败: {str(e)}")
            # 继续执行，使用默认值0
        
        # 获取理财账户余额
        funding_balance = {}
        try:
            funding_balance = await trader.exchange.fetch_funding_balance()
        except Exception as e:
            logging.error(f"获取理财账户余额失败: {str(e)}")
        
        # 安全地获取网格参数 - 添加属性检查
        grid_size = 0
        grid_size_decimal = 0
        threshold = 0
        
        if hasattr(trader, 'grid_size'):
            grid_size = trader.grid_size
            grid_size_decimal = grid_size / 100 if grid_size else 0
            threshold = grid_size_decimal / 5
        else:
            # 对于TrendTrader，使用默认值
            grid_size = 0
            grid_size_decimal = 0
            threshold = 0
            logging.debug("交易者没有grid_size属性，使用默认值0")
        
        # 计算总资产
        SYMBOL = trader.config.SYMBOL if hasattr(trader.config, 'SYMBOL') else 'BNB/USDT'
        SYMBOL_BASE = SYMBOL.split('/')[0] if '/' in SYMBOL else 'BNB'
        SYMBOL_QUOTE = SYMBOL.split('/')[1] if '/' in SYMBOL else 'USDT'
        bnb_balance = float(balance['total'].get(SYMBOL_BASE, 0))
        usdt_balance = float(balance['total'].get(SYMBOL_QUOTE, 0))
        total_assets = usdt_balance + (bnb_balance * current_price)
        
        # 计算总盈亏和盈亏率
        initial_principal = getattr(trader.config, 'INITIAL_PRINCIPAL', 0)
        total_profit = 0.0
        profit_rate = 0.0
        if initial_principal > 0:
            total_profit = total_assets - initial_principal
            profit_rate = (total_profit / initial_principal) * 100
        else:
            logging.warning("初始本金未设置或为0，无法计算盈亏率")
        
        # 安全地获取交易信息
        last_trade_price = getattr(trader, 'last_trade_price', 0)
        last_trade_time = getattr(trader, 'last_trade_time', None)
        last_trade_time_str = datetime.fromtimestamp(last_trade_time).strftime('%Y-%m-%d %H:%M:%S') if last_trade_time else '--'
        
        # 获取交易历史
        trade_history = []
        if hasattr(trader, 'order_tracker') and hasattr(trader.order_tracker, 'get_trade_history'):
            try:
                trades = trader.order_tracker.get_trade_history()
                trade_history = [{
                    'timestamp': datetime.fromtimestamp(trade['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                    'side': trade.get('side', '--'),
                    'price': trade.get('price', 0),
                    'amount': trade.get('amount', 0),
                    'profit': trade.get('profit', 0)
                } for trade in trades[-10:]]  # 只取最近10笔交易
            except Exception as e:
                logging.error(f"获取交易历史失败: {str(e)}")
        
        # 安全地计算目标委托金额
        target_order_amount = 0
        if hasattr(trader, '_calculate_order_amount') and callable(trader._calculate_order_amount):
            try:
                target_order_amount = await trader._calculate_order_amount('buy')
            except Exception as e:
                logging.error(f"计算目标委托金额失败: {str(e)}")
        
        # 安全地获取仓位百分比
        position_ratio = 0
        position_percentage = 0
        if hasattr(trader, 'risk_manager') and hasattr(trader.risk_manager, '_get_position_ratio'):
            try:
                position_ratio = await trader.risk_manager._get_position_ratio()
                position_percentage = position_ratio * 100
            except Exception as e:
                logging.error(f"获取仓位百分比失败: {str(e)}")
        
        # 获取 S1 高低价
        s1_high = getattr(s1_controller, 's1_daily_high', None) if s1_controller else None
        s1_low = getattr(s1_controller, 's1_daily_low', None) if s1_controller else None
        
        # 获取趋势分析数据
        trend_data = await get_trend_analysis_data(symbol=SYMBOL, limit=10)
        
        # 获取合约持仓数据（如果是TrendTrader）
        contract_position = None
        atr = None
        risk_per_trade = None
        sl_atr_multiplier = None
        tp_atr_multiplier = None
        is_consolidating = None
        
        # 检查是否是TrendTrader并获取特定属性
        if is_trend_trader:
            # 合约持仓信息
            try:
                # 尝试获取合约持仓状态
                positions = await trader.exchange.fetch_positions(symbols=[SYMBOL])
                current_position = getattr(trader, 'current_position', None)
                
                if current_position and hasattr(trader, 'entry_price') and trader.entry_price:
                    # 有持仓，计算浮动盈亏
                    unrealized_pnl = 0
                    position_size = getattr(trader, 'position_size', 0)
                    
                    if current_position == 'long':
                        unrealized_pnl = (current_price - trader.entry_price) * position_size
                    else:  # short
                        unrealized_pnl = (trader.entry_price - current_price) * position_size
                        
                    contract_position = {
                        'side': current_position,
                        'size': position_size,
                        'leverage': getattr(trader.config, 'LEVERAGE', 1),
                        'entry_price': trader.entry_price,
                        'stop_loss': getattr(trader, 'stop_loss', None),
                        'take_profit': getattr(trader, 'take_profit', None),
                        'unrealized_pnl': unrealized_pnl
                    }
            except Exception as e:
                logging.error(f"获取合约持仓信息失败: {str(e)}")
                
            # ATR风控信息
            atr = getattr(trader, 'current_atr', None)
            risk_per_trade = getattr(trader, 'risk_per_trade', None)
            sl_atr_multiplier = getattr(trader, 'sl_atr_multiplier', None)
            tp_atr_multiplier = getattr(trader, 'tp_atr_multiplier', None)
            
            # 判断是否震荡市场
            if hasattr(trader, 'is_consolidation') and callable(trader.is_consolidation):
                try:
                    is_consolidating = trader.is_consolidation()
                except Exception as e:
                    logging.error(f"判断震荡行情失败: {str(e)}")
                    
            # 获取开仓信号信息
            entry_signal = getattr(trader, 'entry_signal', None)
            can_open_position = False
            order_status = '--'
            
            # 判断是否可以开仓
            if hasattr(trader, 'can_open_position') and callable(trader.can_open_position):
                try:
                    can_open_position = await trader.can_open_position()
                except Exception as e:
                    logging.error(f"检查是否可以开仓失败: {str(e)}")
            
            # 获取当前挂单状态
            if hasattr(trader, 'open_orders') and trader.open_orders:
                order_status = f"有{len(trader.open_orders)}个挂单"
            elif hasattr(trader, 'opening_position') and trader.opening_position:
                order_status = "正在开仓"
            elif hasattr(trader, 'closing_position') and trader.closing_position:
                order_status = "正在平仓"
            else:
                order_status = "无挂单"
        
        # 获取交易启用状态
        trading_enabled = False
        if is_trend_trader:
            trading_enabled = getattr(trader.config, 'ENABLE_TREND_TRADING', False)
        else:
            trading_enabled = getattr(trader.config, 'ENABLE_GRID_TRADING', False)
        
        # 构建响应数据
        status = {
            "base_price": getattr(trader, 'base_price', 0),
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
            "trend_data": trend_data,
            "trading_enabled": trading_enabled,
            "is_trend_trader": is_trend_trader,
            # 合约相关数据
            "contract_position": contract_position,
            "atr": atr,
            "risk_per_trade": risk_per_trade,
            "sl_atr_multiplier": sl_atr_multiplier,
            "tp_atr_multiplier": tp_atr_multiplier,
            "is_consolidating": is_consolidating,
            "entry_signal": entry_signal,
            "can_open_position": can_open_position,
            "order_status": order_status
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
                # 只返回指定数量的最新记录，但不进行顺序反转，保持文件中的原始顺序
                history = history[-limit:] if limit > 0 else history
        
        return {
            'latest': latest_signal,
            'history': history
        }
    except Exception as e:
        logging.error(f"读取趋势分析数据失败: {str(e)}", exc_info=True)
        return {'latest': None, 'history': []} 