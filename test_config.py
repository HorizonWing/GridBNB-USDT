#!/usr/bin/env python3
"""
配置测试脚本
用于验证虚拟交易配置是否能正确从.env文件中读取
"""

from config import settings

def test_simulation_config():
    """测试虚拟交易配置"""
    print("=" * 50)
    print("虚拟交易配置测试")
    print("=" * 50)
    
    print(f"SIMULATION: {settings.SIMULATION} (类型: {type(settings.SIMULATION)})")
    print(f"SIMULATION_INITIAL_BALANCE: {settings.SIMULATION_INITIAL_BALANCE} (类型: {type(settings.SIMULATION_INITIAL_BALANCE)})")
    
    print("\n其他相关配置:")
    print(f"SYMBOLS: {settings.SYMBOLS}")
    print(f"BINANCE_API_KEY: {'已设置' if settings.BINANCE_API_KEY else '未设置'}")
    print(f"BINANCE_API_SECRET: {'已设置' if settings.BINANCE_API_SECRET else '未设置'}")
    
    if settings.SIMULATION:
        print(f"\n🎯 虚拟交易模式已启用")
        print(f"📊 初始虚拟资金: {settings.SIMULATION_INITIAL_BALANCE} USDT")
        print("⚠️  注意：所有交易都是虚拟的，不会影响真实资金")
    else:
        print(f"\n💰 真实交易模式")
        print("⚠️  注意：将使用真实资金进行交易")
    
    print("=" * 50)

if __name__ == "__main__":
    test_simulation_config()