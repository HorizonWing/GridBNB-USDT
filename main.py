import asyncio
import logging
import traceback
import platform
import sys
from trader import GridTrader
from trend_trader import TrendTrader, run_trend_trader
from helpers import LogConfig, send_pushplus_message
from web_server import start_web_server
from exchange_client import ExchangeClient
from config import TradingConfig
from trend_analyzer import start_trend_analyzer

# 在Windows平台上设置SelectorEventLoop
if platform.system() == 'Windows':
    import asyncio
    # 在Windows平台上强制使用SelectorEventLoop
    if sys.version_info[0] == 3 and sys.version_info[1] >= 8:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        logging.info("已设置Windows SelectorEventLoop策略")

async def main():
    try:
        # 初始化统一日志配置
        LogConfig.setup_logger()
        logging.info("="*50)
        logging.info("交易系统启动")
        logging.info("="*50)
        
        # 创建交易所客户端和配置实例
        exchange = ExchangeClient()
        config = TradingConfig()
        
        # 检查API权限
        try:
            # 尝试加载市场数据
            if not exchange.markets_loaded:
                await exchange.load_markets()
            
            # 尝试获取合约持仓信息以检查API权限
            positions = await exchange.fetch_positions([config.SYMBOL])
            logging.info("API权限检查: 合约交易权限正常")
        except Exception as e:
            error_str = str(e)
            if "Invalid API-key" in error_str or "IP, or permissions" in error_str:
                logging.warning("="*50)
                logging.warning("API权限警告: 当前API密钥没有合约交易权限或IP白名单未设置")
                logging.warning("系统将以有限功能模式运行，合约交易相关功能将不可用")
                logging.warning("如需使用完整功能，请更新您的API权限设置")
                logging.warning("="*50)
                # 发送通知
                send_pushplus_message("API权限不足，合约交易功能不可用。请更新您的API权限设置。", "API权限警告")
            else:
                logging.warning(f"API权限检查过程中发生未知错误: {str(e)}")
        
        # 根据配置选择使用网格交易或趋势交易
        use_trend_trading = config.USE_TREND_TRADING if hasattr(config, 'USE_TREND_TRADING') else True
        
        if use_trend_trading:
            # 使用趋势交易系统
            logging.info("启动趋势交易系统")
            trader = TrendTrader(exchange, config)
            # 初始化交易器
            await trader.initialize()
            
            # 启动Web服务器
            web_server_task = asyncio.create_task(start_web_server(trader))
            
            # 启动交易循环
            trading_task = asyncio.create_task(trader.trading_loop())
            
            # 等待所有任务完成
            await asyncio.gather(web_server_task, trading_task)
        else:
            # 使用网格交易系统
            logging.info("启动网格交易系统")
            # 使用正确的参数初始化交易器
            trader = GridTrader(exchange, config)
            
            # 初始化交易器
            await trader.initialize()

            # 启动趋势分析
            if config.ENABLE_TREND_ANALYZER:
                trend_analyzer_task = asyncio.create_task(start_trend_analyzer(symbol=config.SYMBOL,
                                                                           simulation_mode=False,
                                                                           output_dir=config.TREND_OUTPUT_DIR,
                                                                           interval=config.TREND_INTERVAL))
            else:
                logging.info("趋势分析未启用")
            
            # 启动Web服务器
            web_server_task = asyncio.create_task(start_web_server(trader))
            
            # 启动交易循环
            trading_task = asyncio.create_task(trader.main_loop())
            
            # 等待所有任务完成
            if config.ENABLE_TREND_ANALYZER:
                await asyncio.gather(web_server_task, trading_task, trend_analyzer_task)
            else:
                await asyncio.gather(web_server_task, trading_task)
        
    except Exception as e:
        error_msg = f"启动失败: {str(e)}\n{traceback.format_exc()}"
        logging.error(error_msg)
        send_pushplus_message(error_msg, "致命错误")
        
    finally:
        if 'trader' in locals():
            try:
                await trader.exchange.close()
                logging.info("交易所连接已关闭")
            except Exception as e:
                logging.error(f"关闭连接时发生错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 