# 股票数据更新

本项目使用 Tushare Pro 维护中国股票和指数日频数据。旧 CSMAR 数据、代码和清单已整体归档，
不参与当前更新流程。

## 项目结构

```text
stock/
├─ backup/
│  └─ csmar_snapshot_migrated_2026-08-04/  # 只读旧数据快照
├─ data/
│  ├─ market_data.pkl                       # 程序使用的完整历史数据
│  └─ market_data.xlsx                      # WPS/Excel 查看副本
├─ scripts/
│  └─ update_daily.ps1                      # Windows 计划任务入口
├─ src/
│  ├─ __init__.py
│  ├─ tushare_pipeline.py                    # 下载、连接和数据校验
│  └─ update.py                              # 缺口检查、追加和原子写入
├─ .env
├─ .env.example
├─ .gitignore
├─ README.md
└─ requirements.txt
```

`data/`、`.env` 和 CSMAR 大文件都被 Git 忽略。Git 只保存代码、配置说明和旧快照的清单/代码。

## 安装与 Token

```powershell
python -m pip install -r requirements.txt
```

在项目根目录 `.env` 中填写 Tushare 个人中心提供的 Token：

```dotenv
TUSHARE_TOKEN=你的Token
```

当前接口集合按 Tushare Pro 2000 积分权限设计，包括交易日历、当前上市股票名单、A 股日线、
每日指标、复权因子、涨跌停价格、停复牌事件和四个指数日线。

## 数据文件

`data/market_data.pkl` 是唯一完整数据源，使用 `pandas.to_pickle` 保存以下字典：

```python
{
    "schema_version": 1,
    "source": "tushare_pro",
    "updated_at_utc": "...",
    "stocks": stocks_dataframe,
    "indexes": indexes_dataframe,
}
```

读取方式：

```python
import pandas as pd

bundle = pd.read_pickle("data/market_data.pkl")
stocks = bundle["stocks"]
indexes = bundle["indexes"]
```

`stocks` 以 `trade_date + ts_code` 为主键，按日期和代码升序排列。每个交易日以下载当时的
`stock_basic` 当前上市名单为主表，再左连接 `daily`、`daily_basic`、`adj_factor`、
`stk_limit` 和聚合后的 `suspend_d`。因此没有日线的当前上市股票仍保留一行，价格为空；
只出现在涨跌停接口中的 ETF、基金不会进入股票表。

首次迁移的 50 个历史分区使用同一份当前上市名单快照，每日 5,538 只，共 276,900 行。
源 `daily.csv` 共 275,848 行，其中 189 行属于已不在当前上市名单中的 13 个历史代码，按上述
主表规则不进入 `stocks`；最终非空日线为 275,659 行。这是当前名单口径的必然结果，不代表
源日线丢失或连接失败。真正的历史时点股票池应在后续研究阶段结合 `list_date`、
`delist_date` 和实际行情另行构造。

`indexes` 保留 Tushare 原始 11 列，每个交易日固定包含：

- `000001.SH`：上证指数
- `000300.SH`：沪深300
- `000852.SH`：中证1000
- `000905.SH`：中证500

`data/market_data.xlsx` 只用于查看，工作表只有 `stocks` 和 `indexes`。完整历史以 Pickle
为准；当股票历史超过 Excel 上限时，只选择能够完整放入的最近若干交易日，不截断任何一天。

## 手动更新

补齐从现有最早日期到默认结束日期之间的全部缺口：

```powershell
python -m src.update
```

只检查指定区间：

```powershell
python -m src.update --start 2026-05-27 --end 2026-08-05
```

如果两个数据文件丢失，需要使用 Tushare Token 重新下载，首次运行必须指定开始日期：

```powershell
python -m src.update --start 2026-05-27
```

日期支持 `YYYYMMDD` 和 `YYYY-MM-DD`。默认结束日期按北京时间确定：18:00 及以后检查当日，
18:00 前检查前一日；周末和休市日由上交所交易日历排除。

更新过程先从 Pickle 获取已有完整交易日，然后只为缺失交易日在内存中下载并连接数据，不再
生成 CSV、日分区或 manifest。全部数据通过主键、日期、市场覆盖、四个指数和字段一致性检查后，
程序生成并重新读取临时 Pickle 与 Excel，最后原子替换正式文件。任一步失败都会返回非零退出码，
不会把半成品追加进正式 Pickle。

即使没有新交易日，程序也会从正式 Pickle 重建 Excel。这样可以自动修复进程恰好在 Pickle
替换成功、Excel 替换前中断所造成的短暂不同步。

## Windows 自动更新

计划任务 `StockTushareDailyUpdate` 在周一至周五 18:30 运行
`scripts/update_daily.ps1`。PowerShell 脚本只调用 Python 并原样返回退出码，不创建日志、
状态 JSON 或 Excel 状态页。

查看任务和最近结果：

```powershell
Get-ScheduledTask -TaskName StockTushareDailyUpdate
Get-ScheduledTaskInfo -TaskName StockTushareDailyUpdate
```

`LastTaskResult` 为 `0` 表示成功。后台失败时只保留 Windows 返回码；需要查看具体异常时，
请在项目根目录手动运行 `python -m src.update`。

## CSMAR 备用快照

旧快照位于 `backup/csmar_snapshot_migrated_2026-08-04/`。其中原始数据、旧合并结果、旧代码
（包括归档的 `test_csmar_download.py`）和 `manifest.sha256.csv` 保持原样。当前 Tushare
更新流程不会读取、修改或删除该目录。
