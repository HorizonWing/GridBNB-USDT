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
        
        # 初始化交易器
        # 根据配置决定初始化哪种交易器
        trend_trader = None
        grid_trader = None
        tasks = []
        
        # 根据选择初始化相应的交易器
        if config.USE_TREND_TRADING:
            # 初始化趋势交易器
            logging.info("初始化趋势交易系统")
            trend_trader = TrendTrader(exchange, config)
            await trend_trader.initialize()
            
            # 仅当启用趋势交易时，才添加交易任务
            if config.ENABLE_TREND_TRADING:
                logging.info("启用趋势交易循环")
                tasks.append(asyncio.create_task(trend_trader.trading_loop()))
            else:
                logging.info("趋势交易已初始化但未启用交易功能，仅监控模式")
                
            # 交易器用于Web服务器显示状态
            trader = trend_trader
        else:
            # 初始化网格交易器
            logging.info("初始化网格交易系统")
            grid_trader = GridTrader(exchange, config)
            await grid_trader.initialize()
            
            # 仅当启用网格交易时，才添加交易任务
            if config.ENABLE_GRID_TRADING:
                logging.info("启用网格交易循环")
                tasks.append(asyncio.create_task(grid_trader.main_loop()))
            else:
                logging.info("网格交易已初始化但未启用交易功能，仅监控模式")
                
            # 启动趋势分析（如果启用）
            if config.ENABLE_TREND_ANALYZER:
                trend_analyzer_task = asyncio.create_task(
                    start_trend_analyzer(
                        symbol=config.SYMBOL,
                        simulation_mode=False,
                        output_dir=config.TREND_OUTPUT_DIR,
                        interval=config.TREND_INTERVAL
                    )
                )
                tasks.append(trend_analyzer_task)
            else:
                logging.info("趋势分析未启用")
                
            # 交易器用于Web服务器显示状态
            trader = grid_trader
        
        # 启动Web服务器
        web_server_task = asyncio.create_task(start_web_server(trader))
        tasks.append(web_server_task)
        
        # 等待所有任务完成
        await asyncio.gather(*tasks)
        
    except Exception as e:
        error_msg = f"启动失败: {str(e)}\n{traceback.format_exc()}"
        logging.error(error_msg)
        send_pushplus_message(error_msg, "致命错误")
        
    finally:
        # 关闭连接
        try:
            await exchange.close()
            logging.info("交易所连接已关闭")
        except Exception as e:
            logging.error(f"关闭连接时发生错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 