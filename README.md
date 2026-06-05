# RGPoly 使用手册

RGPoly 是一个自用 Polymarket 钱包跟单交易工具。它做四件事：

1. 监控你配置的钱包。
2. 发现目标钱包买入后生成信号。
3. 按你的价格、金额、关键词、风控条件筛选。
4. 生成订单；dry-run 模式只模拟，live 模式会真实下单。

## 你每天怎么用

在项目根目录打开 PowerShell：

```powershell
cd C:\Users\王大喜\Documents\Codex\2026-06-05\files-mentioned-by-the-user-polymarket\work\polymarket-copytrading-dev
```

开第一个窗口，启动中文控制台：

```powershell
python -m rgpoly --config .\config\rgpoly.toml dashboard-server
```

浏览器打开：

```text
http://127.0.0.1:8765/
```

开第二个窗口，先 dry-run 跑：

```powershell
python -m rgpoly --config .\config\rgpoly.toml run --dry-run
```

确认信号、拒绝原因、订单都符合预期后，再开实盘：

```powershell
$env:RGPOLY_LIVE_ENABLED="I_UNDERSTAND_REAL_MONEY_RISK"
python -m rgpoly --config .\config\rgpoly.toml run --live --execute-limit 1
```

`run --live` 是会真实下单的命令。刚开始保留 `--execute-limit 1`。

## 配置改哪里

你主要改这个文件：

```text
config\rgpoly.toml
```

这个文件是本地实际运行配置，默认不会提交到 GitHub。模板文件是：

```text
config\rgpoly.example.toml
```

如果本地配置不存在：

```powershell
python -m rgpoly init-config --path .\config\rgpoly.toml
```

## 最重要的配置项

执行模式：

```toml
[execution]
mode = "dry_run"            # manual | dry_run | live
execute_limit_per_loop = 10
max_daily_usdc = 50.0
max_open_intents = 25
order_type = "FOK"
```

含义：

- `manual`：只监控，只生成待执行订单，不自动成交。
- `dry_run`：模拟成交，不花真钱。
- `live`：真实下单。

跟单策略：

```toml
[[wallet_copy]]
name = "smart_crypto_copy"
enabled = true
stake_usdc = 10.0
min_entry_price = 0.10
max_price = 0.65
max_source_to_ask_gap = 0.01
min_ask_depth_usdc = 30.0
min_source_usdc = 3.0
max_signal_age_sec = 8
required_title_keywords = ["bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp"]
blocked_title_keywords = []
allowed_outcomes = ["Up", "Down", "Yes", "No"]

[wallet_copy.wallets]
my_wallet_alias = "0x..."
```

常改字段：

- `enabled`：这个策略是否启用。
- `stake_usdc`：每次跟单买多少钱。
- `max_price`：最高接受价格，高于这个价格不追。
- `max_signal_age_sec`：信号最多允许多旧，越小越快。
- `required_title_keywords`：市场标题必须包含这些关键词之一。
- `blocked_title_keywords`：标题命中这些词就拒绝。
- `allowed_outcomes`：允许买哪些结果。
- `[wallet_copy.wallets]`：要监控的钱包地址。

## 第一次安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\requirements.txt
python -m rgpoly init-config --path .\config\rgpoly.toml
python -m rgpoly --config .\config\rgpoly.toml migrate
python -m rgpoly --config .\config\rgpoly.toml doctor
```

## 实盘前准备

密钥不写进 `config\rgpoly.toml`，放 PowerShell 环境变量：

```powershell
$env:PRIVATE_KEY="..."
$env:POLY_API_KEY="..."
$env:POLY_API_SECRET="..."
$env:POLY_API_PASSPHRASE="..."
$env:POLY_SIGNATURE_TYPE="3"
$env:POLY_PROXY_ADDRESS="0x..."
```

只有私钥、没有 Polymarket L2 API key 时：

```powershell
python -m rgpoly --config .\config\rgpoly.toml derive-api-key
```

实盘前检查：

```powershell
$env:RGPOLY_LIVE_ENABLED="I_UNDERSTAND_REAL_MONEY_RISK"
python -m rgpoly --config .\config\rgpoly.toml doctor --live --check-client
```

## 常用命令

```powershell
# 检查配置、数据库、ready intent 数量
python -m rgpoly --config .\config\rgpoly.toml doctor

# 拉一次钱包活动
python -m rgpoly --config .\config\rgpoly.toml poll-once

# 看当前统计
python -m rgpoly --config .\config\rgpoly.toml status

# 看待执行订单
python -m rgpoly --config .\config\rgpoly.toml intents

# 中文控制台
python -m rgpoly --config .\config\rgpoly.toml dashboard-server

# 连续模拟
python -m rgpoly --config .\config\rgpoly.toml run --dry-run

# 连续实盘
python -m rgpoly --config .\config\rgpoly.toml run --live --execute-limit 1
```

## 前端看到什么

中文控制台会显示：

- 钱包活动数量。
- 信号数量、通过数量、拒绝数量。
- 待执行订单。
- 模拟成交、实盘成交、失败订单。
- 最近信号和拒绝原因。
- 最近执行回执。

控制台直接读 `.runtime\rgpoly.sqlite`，刷新浏览器就能看到最新数据。

## 这个项目不会自动帮你判断能不能赚钱

它只是一个快速跟单执行工具。是否该跟、跟谁、多少钱、什么价格上限，都由
`config\rgpoly.toml` 控制。实盘前先小金额 dry-run，看清楚拒绝原因和订单行为。
