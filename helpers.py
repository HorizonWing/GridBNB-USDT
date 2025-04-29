import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from config import PUSHPLUS_TOKEN
from config import PUSH_URL
import time
import psutil
import os
from logging.handlers import TimedRotatingFileHandler

def format_trade_message(side, symbol, price, amount, total, grid_size, retry_count=None):
    """格式化交易消息为美观的文本格式
    
    Args:
        side (str): 交易方向 ('buy' 或 'sell')
        symbol (str): 交易对
        price (float): 交易价格
        amount (float): 交易数量
        total (float): 交易总额
        grid_size (float): 网格大小
        retry_count (tuple, optional): 重试次数，格式为 (当前次数, 最大次数)
    
    Returns:
        str: 格式化后的消息文本
    """
    # 使用emoji增加可读性
    direction_emoji = "🟢" if side == 'buy' else "🔴"
    direction_text = "买入" if side == 'buy' else "卖出"
    
    # 解析交易对获取币种
    base_currency = symbol.split('/')[0] if '/' in symbol else 'BNB'
    quote_currency = symbol.split('/')[1] if '/' in symbol else 'USDT'
    
    # 构建消息主体
    message = f"""
{direction_emoji} {direction_text} {symbol}
━━━━━━━━━━━━━━━━━━━━
💰 价格：{price:.2f} {quote_currency}
📊 数量：{amount:.4f} {base_currency}
💵 金额：{total:.2f} {quote_currency}
📈 网格：{grid_size}%
"""
    
    # 如果有重试信息，添加重试次数
    if retry_count:
        current, max_retries = retry_count
        message += f"🔄 尝试：{current}/{max_retries}次\n"
    
    # 添加时间戳
    message += f"⏰ 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}"
    
    return message

def format_signal_message(signal_data):
    """格式化交易信号消息为美观的文本格式
    
    Args:
        signal_data (dict): 包含交易信号信息的字典
    
    Returns:
        str: 格式化后的信号消息文本
    """
    # 获取信号数据
    signal = signal_data.get('signal', '未知')
    symbol = signal_data.get('symbol', '未知')
    current_price = signal_data.get('current_price', 0)
    position_size = signal_data.get('position_size', 0)
    stop_loss = signal_data.get('stop_loss', 0)
    take_profit = signal_data.get('take_profit', 0)
    trend_aligned = signal_data.get('trend_aligned', False)
    long_trend = signal_data.get('long_trend', '未知')
    mid_trend = signal_data.get('mid_trend', '未知')
    short_trend = signal_data.get('short_trend', '未知')
    timestamp = signal_data.get('timestamp', time.strftime('%Y-%m-%d %H:%M:%S'))
    advice = signal_data.get('advice', '未知')
    position_ratio = signal_data.get('position_ratio', 0)
    confidence = signal_data.get('confidence', '未知')
    market_state = signal_data.get('market_state', '未知')
    
    # 根据信号类型选择emoji
    signal_emoji = {
        '买入': '🟢',
        '卖出': '🔴',
        '持有': '🟡',
        '观望': '⚪'
    }.get(signal, '❓')
    
    # 解析交易对获取币种
    base_currency = symbol.split('/')[0] if '/' in symbol else 'BNB'
    quote_currency = symbol.split('/')[1] if '/' in symbol else 'USDT'
    
    # 构建信号消息
    message = f"""
{signal_emoji} {signal}信号 - {symbol}
━━━━━━━━━━━━━━━━━━━━
💰 当前价格: {current_price:.2f} {quote_currency}
📊 建议操作: {advice}
🎯 仓位比例: {position_ratio:.2f} ({position_ratio*100:.0f}%)
"""
    
    # 如果有止损止盈信息且不为0
    if stop_loss > 0 and take_profit > 0:
        message += f"""
🛑 止损价位: {stop_loss:.2f} {quote_currency}
💹 止盈价位: {take_profit:.2f} {quote_currency}
"""
    
    # 添加趋势信息
    trend_status = "✅ 趋势一致" if trend_aligned else "⚠️ 趋势不一致"
    message += f"""
📈 趋势分析: {trend_status}
  • 长期: {long_trend}
  • 中期: {mid_trend}
  • 短期: {short_trend}
"""
    
    # 添加信心度和市场状态
    confidence_emoji = {
        '高': '🔥',
        '中': '⚡',
        '低': '❄️'
    }.get(confidence, '❓')
    
    message += f"""
{confidence_emoji} 信心指数: {confidence}
🌐 市场状态: {market_state}
⏰ 分析时间: {timestamp}
"""
    
    return message


def send_pushplus_message(content, title="交易信号通知"):
    if not PUSHPLUS_TOKEN:
        logging.error("未配置PUSHPLUS_TOKEN，无法发送通知")
        return
    
    url = PUSH_URL if PUSH_URL else "https://push.cdnfast.link/api/push/w8IsyyvW0PpZCbqs"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "title": title,
        "content": content,
    }
    try:
        logging.info(f"正在发送推送通知: {title}")
        response = requests.post(url, json=data, headers=headers)
        response_json = response.json()
        
        if response.status_code == 200 and response_json.get('code') == 200:
            logging.info(f"消息推送成功: {content}")
        else:
            logging.error(f"消息推送失败: 状态码={response.status_code}, 响应={response_json}, 地址：{url}")
    except Exception as e:
        logging.error(f"消息推送异常: {str(e)}", exc_info=True)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def safe_fetch(method, *args, **kwargs):
    try:
        return await method(*args, **kwargs)
    except Exception as e:
        logging.error(f"请求失败: {str(e)}")
        raise 

def debug_watcher():
    """资源监控装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.time()
            mem_before = psutil.virtual_memory().used
            logging.debug(f"[DEBUG] 开始执行 {func.__name__}")
            
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                cost = time.time() - start
                mem_used = psutil.virtual_memory().used - mem_before
                logging.debug(f"[DEBUG] {func.__name__} 执行完成 | 耗时: {cost:.3f}s | 内存变化: {mem_used/1024/1024:.2f}MB")
        return wrapper
    return decorator 

class LogConfig:
    SINGLE_LOG = True  # 强制单文件模式
    BACKUP_DAYS = 2    # 保留2天日志
    LOG_DIR = os.path.dirname(__file__)  # 与main.py相同目录
    LOG_LEVEL = logging.INFO

    @staticmethod
    def setup_logger():
        logger = logging.getLogger()
        logger.setLevel(LogConfig.LOG_LEVEL)
        
        # 清理所有现有处理器
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # 文件处理器
        file_handler = TimedRotatingFileHandler(
            os.path.join(LogConfig.LOG_DIR, 'trading_system.log'),
            when='midnight',
            interval=1,
            backupCount=LogConfig.BACKUP_DAYS,
            encoding='utf-8',
            delay=True
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    @staticmethod
    def clean_old_logs():
        if not os.path.exists(LogConfig.LOG_DIR):
            return
        now = time.time()
        for fname in os.listdir(LogConfig.LOG_DIR):
            if LogConfig.SINGLE_LOG and fname != 'trading_system.log':
                continue
            path = os.path.join(LogConfig.LOG_DIR, fname)
            if os.stat(path).st_mtime < now - LogConfig.BACKUP_DAYS * 86400:
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"删除旧日志失败 {fname}: {str(e)}") 