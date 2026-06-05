# RGPoly

RGPoly 是一个自用的 Polymarket 钱包跟单交易引擎。当前仓库只保留 v2：
监控目标钱包、生成信号、做风控、生成订单意图，然后 dry-run 或实盘下单。

## 配置在哪里

你平时主要改这两个地方：

- `config/rgpoly.toml`：本地实际运行配置，默认不提交到 GitHub。
- `config/rgpoly.example.toml`：仓库里的配置模板，用来复制出本地配置。

如果你本地还没有 `config/rgpoly.toml`，先生成：

```powershell
python -m rgpoly init-config --path .\config\rgpoly.toml
```

配置文件里最重要的是：

```toml
[engine]
db_path = ".runtime/rgpoly.sqlite"       # 本地 SQLite 数据库
poll_interval_ms = 750                   # 轮询间隔，毫秒
activity_limit = 20                      # 每个钱包每轮拉取多少条活动
http_timeout_sec = 4.0                   # Polymarket API 超时

[execution]
mode = "dry_run"                         # manual | dry_run | live
execute_limit_per_loop = 10              # 每轮最多执行多少个 ready intent
max_daily_usdc = 50.0                    # 每日最大花费
max_open_intents = 25                    # 最多保留多少个待执行 intent
order_type = "FOK"                       # FOK | FAK
```

每个 `[[wallet_copy]]` 是一个跟单策略。你要改跟哪个钱包、每单多少 USDC、
最高接受价格、关键词过滤、允许结果，就改这里：

```toml
[[wallet_copy]]
name = "smart_crypto_copy"
enabled = true
stake_usdc = 10.0
max_price = 0.65
max_signal_age_sec = 8
required_title_keywords = ["bitcoin", "btc", "ethereum", "eth"]
allowed_outcomes = ["Up", "Down", "Yes", "No"]

[wallet_copy.wallets]
alias = "0x..."
```

私钥和 Polymarket API key 不写进配置文件，放环境变量。

## 项目结构

```text
rgpoly/                   核心交易引擎
  strategies/             钱包跟单策略
config/                   配置模板
docs/                     架构、安全、数据说明
ops/windows/              Windows 启动、停止、状态脚本
tests/                    单元测试
```

运行链路：

```text
目标钱包活动 -> 信号 -> 风控 -> 订单意图 -> dry-run 回执或实盘回执
```

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\requirements.txt
python -m rgpoly init-config --path .\config\rgpoly.toml
python -m rgpoly --config .\config\rgpoly.toml migrate
python -m rgpoly --config .\config\rgpoly.toml doctor
```

## 本地前端

当前前端是一个本地静态控制台，由 SQLite 数据库生成 HTML。

生成页面：

```powershell
python -m rgpoly --config .\config\rgpoly.toml dashboard --output .\.runtime\index.html
```

拉起本地前端：

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory .runtime
```

浏览器打开：

```text
http://127.0.0.1:8765/
```

注意：页面是静态 HTML。你跑完 `poll-once`、`run` 或 `execute` 后，需要重新生成
`.runtime/index.html` 才能看到最新数据。

## Dry-Run 测试

拉取一次目标钱包活动：

```powershell
python -m rgpoly --config .\config\rgpoly.toml poll-once
```

查看待执行订单：

```powershell
python -m rgpoly --config .\config\rgpoly.toml intents
```

连续 dry-run：

```powershell
python -m rgpoly --config .\config\rgpoly.toml run --dry-run
```

只监控不执行：

```powershell
python -m rgpoly --config .\config\rgpoly.toml run --manual
```

## 实盘

先设置环境变量。真实值不要提交到 GitHub。

```powershell
$env:PRIVATE_KEY="..."
$env:POLY_API_KEY="..."
$env:POLY_API_SECRET="..."
$env:POLY_API_PASSPHRASE="..."
$env:POLY_SIGNATURE_TYPE="3"
$env:POLY_PROXY_ADDRESS="0x..."
```

如果你只有私钥，没有 L2 API key，可以派生：

```powershell
python -m rgpoly --config .\config\rgpoly.toml derive-api-key
```

实盘前检查：

```powershell
$env:RGPOLY_LIVE_ENABLED="I_UNDERSTAND_REAL_MONEY_RISK"
python -m rgpoly --config .\config\rgpoly.toml doctor --live --check-client
```

小额度启动实盘，每轮最多下 1 单：

```powershell
python -m rgpoly --config .\config\rgpoly.toml run --live --execute-limit 1
```

Windows 后台启动：

```powershell
.\ops\windows\start_rgpoly_v2.ps1 -Config config\rgpoly.toml -Mode live -ExecuteLimit 1
.\ops\windows\view_rgpoly_v2_status.ps1 -Config config\rgpoly.toml -Mode live
.\ops\windows\stop_rgpoly_v2.ps1
```

## 常用命令

```powershell
python -m rgpoly --config .\config\rgpoly.toml doctor
python -m rgpoly --config .\config\rgpoly.toml status
python -m rgpoly --config .\config\rgpoly.toml poll-once
python -m rgpoly --config .\config\rgpoly.toml run --dry-run
python -m rgpoly --config .\config\rgpoly.toml run --live --execute-limit 1
python -m rgpoly --config .\config\rgpoly.toml execute
python -m rgpoly --config .\config\rgpoly.toml execute --live --limit 1
python -m rgpoly --config .\config\rgpoly.toml dashboard --output .\.runtime\index.html
```

## 为什么之前实盘不会下单

之前的 v2 有 live executor，但 `rgpoly run` 只负责监控和生成 ready intent，
不会自动执行。现在 `run --live` 已经接通完整闭环：每轮轮询后会消费 ready
intent，并提交到 Polymarket CLOB。

## 安全提醒

实盘前用低余额独立钱包。先 dry-run，看清楚信号、拒绝原因、ready intent 和回执。
刚开始用 `--execute-limit 1` 和小的 `stake_usdc`。确认你所在地区和平台规则允许交易。
