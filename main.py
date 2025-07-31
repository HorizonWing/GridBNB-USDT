import asyncio
import logging
import traceback
import platform
import sys
from trader import GridTrader
from helpers import LogConfig, send_pushplus_message
from web_server import start_web_server
from exchange_client import ExchangeClient
from simulation_exchange import SimulationExchange
from config import TradingConfig, SYMBOLS_LIST, settings

async def periodic_global_status_logger(interval_seconds: int = 60):
    """
    一个独立的后台任务，使用自己独立的ExchangeClient实例，
    周期性地计算并记录真正的全账户总资产。
    【最终修复版】
    """
    logging.info(f"启动全局资产监控任务，每 {interval_seconds} 秒检查一次（仅在变化>1%时记录）。")

    # 1. 为此任务创建专用的、独立的客户端实例，确保数据隔离
    report_client = None
    try:
        report_client = ExchangeClient()
        await report_client.load_markets() # 独立加载市场数据
    except Exception as e:
        logging.critical(f"全局资产监控任务的客户端初始化失败，任务无法启动: {e}")
        return # 如果客户端初始化失败，则直接退出任务

    last_logged_total_value = 0.0

    while True:
        try:
            # 2. 使用专用的客户端进行计算
            current_total_value = await report_client.calculate_total_account_value(quote_currency='USDT')

            if abs(current_total_value - last_logged_total_value) / max(last_logged_total_value, 1e-9) > 0.01:
                logging.info(
                    f"【全局资产报告】当前全账户总价值: {current_total_value:.2f} USDT "
                    f"(较上次记录变化: {current_total_value - last_logged_total_value:+.2f} USDT)"
                )
                last_logged_total_value = current_total_value

            await asyncio.sleep(interval_seconds)

        except asyncio.CancelledError:
            logging.info("全局资产监控任务已取消。")
            break
        except Exception as e:
            logging.error(f"全局资产监控任务发生错误: {e}", exc_info=True)
            await asyncio.sleep(interval_seconds * 2)

    # 任务结束前，安全关闭专用的客户端
    if report_client:
        await report_client.close()
        logging.info("全局资产监控任务的客户端已关闭。")

# 在Windows平台上设置SelectorEventLoop
if platform.system() == 'Windows':
    import asyncio
    # 在Windows平台上强制使用SelectorEventLoop
    if sys.version_info[0] == 3 and sys.version_info[1] >= 8:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        logging.info("已设置Windows SelectorEventLoop策略")

async def run_trader_for_symbol(symbol: str, exchange_client: ExchangeClient):
    """为单个交易对创建并运行一个交易器实例"""
    try:
        logging.info(f"为交易对 {symbol} 创建交易实例...")
        config = TradingConfig()

        # 使用传入的共享客户端
        trader = GridTrader(exchange_client, config, symbol)

        await trader.initialize()
        await trader.main_loop()

    except Exception as e:
        error_msg = f"交易对 {symbol} 的任务失败: {str(e)}\n{traceback.format_exc()}"
        logging.error(error_msg)
        send_pushplus_message(error_msg, f"致命错误 - {symbol}")

async def main():
    shared_exchange_client = None  # 在try块外部定义
    try:
        LogConfig.setup_logger()
        logging.info("="*50)
        logging.info("多币种网格交易系统启动")
        logging.info(f"待运行交易对: {SYMBOLS_LIST}")
        logging.info("="*50)

        if not SYMBOLS_LIST:
            logging.warning("没有配置任何交易对，程序即将退出。")
            return
            
        if len({s.split('/')[1] for s in SYMBOLS_LIST}) > 1:
            logging.warning("计价货币不一致，程序即将退出。")
            return

        # 在主函数中创建唯一、共享的ExchangeClient实例
        shared_exchange_client = ExchangeClient()
        
        # 根据配置决定使用真实交易还是虚拟交易
        if settings.SIMULATION:
            logging.info("=" * 50)
            logging.info("🎯 虚拟交易模式已启用")
            logging.info(f"📊 初始虚拟资金: {settings.SIMULATION_INITIAL_BALANCE} USDT")
            logging.info("⚠️  注意：所有交易都是虚拟的，不会影响真实资金")
            logging.info("=" * 50)
            # 使用虚拟交易所包装真实交易所
            shared_exchange_client = SimulationExchange(shared_exchange_client)
        else:
            logging.info("💰 真实交易模式已启用")

        # 【新增】启动周期性时间同步任务
        await shared_exchange_client.start_periodic_time_sync()

        # 加载一次市场数据供所有实例使用
        await shared_exchange_client.load_markets()
        logging.info("市场数据加载完成，开始创建交易器实例...")

        traders = {}  # 用于存储所有trader实例，供Web服务器使用
        tasks = []

        # 为每个交易对创建trader实例和任务
        for symbol in SYMBOLS_LIST:
            config = TradingConfig()
            trader_instance = GridTrader(shared_exchange_client, config, symbol)
            traders[symbol] = trader_instance

            # 初始化trader
            await trader_instance.initialize()

            # 创建运行任务
            tasks.append(trader_instance.main_loop())

        # 如果有trader实例，启动Web服务器监控所有交易对
        if traders:
            logging.info(f"启动Web服务器监控 {len(traders)} 个交易对...")
            web_server_task = asyncio.create_task(start_web_server(traders))
            tasks.append(web_server_task)

        # 【新增】启动独立的全局资产监控任务
        global_status_task = asyncio.create_task(
            periodic_global_status_logger(interval_seconds=60)
        )
        tasks.append(global_status_task)

        # 并发运行所有任务
        mode_text = "虚拟交易" if settings.SIMULATION else "真实交易"
        logging.info(f"开始并发运行 {len(SYMBOLS_LIST)} 个交易对及其他后台任务...({mode_text}模式)")
        await asyncio.gather(*tasks)

    except Exception as e:
        logging.critical(f"主程序发生未知严重错误: {e}\n{traceback.format_exc()}")

    finally:
        # 统一在此处关闭共享的客户端
        if shared_exchange_client:
            try:
                # 【新增】在关闭连接前，先停止时间同步任务
                await shared_exchange_client.stop_periodic_time_sync()
                await shared_exchange_client.close()
                logging.info("共享的交易所连接已安全关闭")
            except Exception as e:
                logging.error(f"关闭共享连接时发生错误: {str(e)}")

        logging.info("所有交易任务已结束。程序即将退出。")
        
        # 如果是虚拟交易模式，输出交易总结
        if settings.SIMULATION and hasattr(shared_exchange_client, 'get_simulation_summary'):
            try:
                summary = shared_exchange_client.get_simulation_summary()
                logging.info("=" * 60)
                logging.info("🎯 虚拟交易总结报告")
                logging.info(f"📊 总交易次数: {summary.get('total_trades', 0)}")
                logging.info(f"💰 初始资金: {summary.get('initial_balance', 0)} USDT")
                
                current_balances = summary.get('current_balances', {})
                funding_balances = summary.get('funding_balances', {})
                
                logging.info("📈 当前资产分布:")
                for asset, balance in current_balances.items():
                    if balance > 0:
                        logging.info(f"   现货 {asset}: {balance:.8f}")
                        
                for asset, balance in funding_balances.items():
                    if balance > 0:
                        logging.info(f"   理财 {asset}: {balance:.8f}")
                
                # 计算总资产价值变化
                try:
                    final_value = await shared_exchange_client.calculate_total_account_value()
                    initial_value = summary.get('initial_balance', 0)
                    profit_loss = final_value - initial_value
                    profit_percentage = (profit_loss / initial_value * 100) if initial_value > 0 else 0
                    
                    logging.info(f"💹 总资产价值: {final_value:.2f} USDT")
                    logging.info(f"📊 盈亏: {profit_loss:+.2f} USDT ({profit_percentage:+.2f}%)")
                except:
                    pass
                    
                logging.info("=" * 60)
            except Exception as e:
                logging.error(f"生成虚拟交易总结失败: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 