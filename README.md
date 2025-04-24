# BNB/USDT 自动化网格交易机器人

这是一个基于 Python 的自动化交易程序，专为币安 (Binance) 交易所的 BNB/USDT 交易对设计。该程序采用网格交易策略，旨在通过动态调整网格和仓位来捕捉市场波动，并内置风险管理机制。

## 核心功能

*   **自动化网格交易**: 针对 BNB/USDT 交易对执行网格买卖策略。
*   **动态网格调整**: 根据市场波动率自动调整网格大小 (`config.py` 中的 `GRID_PARAMS`)。
*   **多指标组合趋势交易系统**: 通过多周期和多指标分析判断市场趋势，提供交易信号。
*   **风险管理**:
    *   最大回撤限制 (`MAX_DRAWDOWN`)
    *   每日亏损限制 (`DAILY_LOSS_LIMIT`)
    *   最大仓位比例限制 (`MAX_POSITION_RATIO`)
    *   基于ATR的风险仓位计算
*   **Web 用户界面**: 提供一个简单的 Web 界面 (通过 `web_server.py`)，用于实时监控交易状态、账户信息、订单和调整配置。
*   **状态持久化**: 将交易状态保存到 `data/` 目录下的 JSON 文件中，以便重启后恢复。
*   **通知推送**: 可通过 PushPlus 发送重要事件和错误通知 (`PUSHPLUS_TOKEN`)。
*   **日志记录**: 详细的运行日志记录在 `trading_system.log` 文件中。

## 环境要求

*   Python 3.8+
*   依赖库见 `requirements.txt` 文件。

## 安装步骤

1.  **克隆仓库**:
    ```bash
    git clone <你的仓库HTTPS或SSH地址>
    cd GridBNB-USDT
    ```

2.  **创建并激活虚拟环境**:
    *   **Windows**:
        ```bash
        python -m venv .venv
        .\.venv\Scripts\activate
        ```
    *   **Linux / macOS**:
        ```bash
        python3 -m venv .venv
        source .venv/bin/activate
        ```

3.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```

## 配置

1.  **创建 `.env` 文件**:
    在项目根目录下创建一个名为 `.env` 的文件。

2.  **配置环境变量**:
    在 `.env` 文件中添加以下必要的环境变量，并填入你的信息：
    ```dotenv
    # 币安 API (必须)
    BINANCE_API_KEY=YOUR_BINANCE_API_KEY
    BINANCE_API_SECRET=YOUR_BINANCE_API_SECRET

    # PushPlus Token (可选, 用于消息推送)
    PUSHPLUS_TOKEN=YOUR_PUSHPLUS_TOKEN

    # 初始设置 (可选, 影响首次运行和统计)
    INITIAL_PRINCIPAL=1000.0  # 你的初始总资产 (USDT)
    INITIAL_BASE_PRICE=600.0   # 你认为合适的初始基准价格 (用于首次启动确定方向)
    ```
    *   **重要**: 确保你的币安 API Key 具有现货交易权限，但**不要**开启提现权限。

3.  **调整交易参数 (可选)**:
    你可以根据自己的策略需求修改 `config.py` 文件中的参数，例如：
    *   `SYMBOL`: 交易对 (默认为 'BNB/USDT')
    *   `INITIAL_GRID`: 初始网格大小 (%)
    *   `MIN_TRADE_AMOUNT`: 最小交易金额 (USDT)
    *   `MAX_POSITION_RATIO`, `MIN_POSITION_RATIO`: 最大/最小仓位比例
    *   风险参数 (`MAX_DRAWDOWN`, `DAILY_LOSS_LIMIT`)
    *   波动率与网格对应关系 (`GRID_PARAMS['volatility_threshold']`)

## 运行

在激活虚拟环境的项目根目录下运行主程序：

```bash
python main.py
```

程序启动后将开始连接交易所、初始化状态并执行交易逻辑。

### 单独运行趋势分析系统

你可以单独运行趋势分析系统，以获取市场趋势信号：

```bash
python trend_analyzer_runner.py --exchange binance --symbol BTC/USDT
```

参数说明：
- `--exchange`: 交易所ID (默认: binance)
- `--symbol`: 交易对 (默认: BTC/USDT)
- `--output`: 分析结果输出目录 (默认: results)

分析结果将保存在指定目录中，并记录在日志文件中。

### 运行趋势交易系统示例

要运行趋势交易系统的回测示例：

```bash
python trend_system_example.py
```

这将生成示例数据，执行回测，并绘制交易图表。

## 多指标组合趋势交易系统

该系统结合多个技术指标和多周期分析来识别市场趋势和生成交易信号：

### 主要指标

- **均线系统**：使用EMA均线组合（短期、中期、长期）判断趋势方向
- **MACD指标**：确认趋势动能和可能的反转点
- **RSI指标**：检测超买超卖状态和价格背离
- **KDJ指标**：提供动量和潜在反转信号
- **ATR指标**：测量市场波动率，用于仓位管理和止损设置

### 多周期分析

系统同时分析三个不同的时间周期：
- **长周期**（日线/周线）：确定主要趋势方向
- **中周期**（4小时/日线）：确认中期趋势
- **短周期**（1小时/4小时）：寻找精确入场点

### 交易信号生成

交易信号基于以下条件生成：
- 多数指标一致指向同一方向
- 多个时间周期的趋势一致
- 价格与关键均线的关系
- 确认的动量信号

### 风险管理

- **ATR仓位计算**：根据市场波动率动态计算合适的仓位大小
- **阶梯式止损**：随着价格向有利方向移动自动调整止损点
- **风险收益比**：标准设置为1:1.5或以上

## Web 界面

程序启动后，会自动运行一个 Web 服务器。你可以通过浏览器访问以下地址来监控和管理交易机器人：

`http://127.0.0.1:8080`

*注意: 端口号 (8080) 可能在 `web_server.py` 中定义，如果无法访问请检查该文件。*

Web 界面可以让你查看当前状态、账户余额、持仓、挂单、历史记录，并可能提供一些手动操作或配置调整的功能。

## 日志

程序的运行日志会输出到控制台，并同时记录在项目根目录下的 `trading_system.log` 文件中。

## 注意事项

*   **交易风险**: 所有交易决策均由程序自动执行，但市场存在固有风险。请务必了解策略原理和潜在风险，并自行承担交易结果。不建议在未充分理解和测试的情况下投入大量资金。
*   **API Key 安全**: 妥善保管你的 API Key 和 Secret，不要泄露给他人。
*   **配置合理性**: 确保 `config.py` 和 `.env` 中的配置符合你的预期和风险承受能力。

## 贡献

欢迎提交 Pull Requests 或 Issues 来改进项目。
