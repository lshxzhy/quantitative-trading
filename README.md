# 股票数据更新

项目当前使用 Tushare Pro API 下载并校验中国股票市场日频数据。原 CSMAR
数据、爬虫、合并脚本和测试已整体归档，不再参与当前下载流程。

## 项目结构

```text
backup/
  csmar_snapshot_migrated_2026-08-04/
    code/             # 原 CSMAR 代码与测试
    raw/              # 原始 CSMAR ZIP，本地保留且不上传 Git
    processed/        # 原合并 CSV，本地保留且不上传 Git
    manifest.sha256.csv
data/                 # 新 Tushare 数据，本地生成且不上传 Git
src/
  download.py         # 下载命令入口
  update.py           # 连续补齐缺失交易日的日更入口
  tushare_pipeline.py # 接口调用、校验与原子落盘
tests/
  test_tushare_pipeline.py
```

## 准备环境

```powershell
python -m pip install -r requirements.txt
```

当前下载集合按 Tushare Pro 2000 积分权限设计，包含股票基础信息、交易日历、
A 股日线、每日指标、复权因子、每日涨跌停价格、每日停复牌信息和指数日线。
2000 积分档存在接口频率限制，但单个交易日的完整下载约发起 11 次请求，批量更新
另有 1 次交易日历请求，不需要额外提高积分才能完成日更。

复制 `.env.example` 中的配置项到本地 `.env`，填入在 Tushare 个人中心获取的
Token：

```dotenv
TUSHARE_TOKEN=你的Token
```

`.env`、`data/`、CSMAR 大文件和浏览器状态均已被 Git 忽略。

## 下载一个交易日

```powershell
python -m src.download --date 2026-05-26
```

## 首次补齐与日常更新

旧 CSMAR 个股数据截至 2026-05-26。首次接通 Tushare 后，从下一天开始补齐：

```powershell
python -m src.update --start 2026-05-27
```

更新命令先读取上交所交易日历，只下载区间内尚不存在的开市日；已有日期分区会明确
跳过。第一次成功写入后，日常运行不再需要指定开始日期：

```powershell
python -m src.update
```

程序会从本地最新 `trade_date=YYYYMMDD` 分区的下一天继续。默认结束日期按北京时间
确定：18:00 及以后使用当天，18:00 前使用前一天，避免每日指标尚未全部入库。
周末和节假日由交易日历自动排除。也可以用 `--end YYYY-MM-DD` 明确指定结束日。

日期支持 `YYYYMMDD` 和 `YYYY-MM-DD`。脚本依次检查：

1. 指定日期是上交所交易日；
2. 上市股票列表包含沪、深、北三个交易所；
3. 日线、每日指标、复权因子、涨跌停和停复牌接口字段完整；
4. 日线包含沪、深、北三个市场且主键不重复；
5. `000001.SH`、`000300.SH`、`000852.SH`、`000905.SH` 四个指数齐全；
6. 每个 CSV 的行数、字节数和 SHA-256 被写入 `manifest.json`。

数据先写入 `data/.staging/tushare/<交易日>/`。所有接口和校验全部通过后，
整个目录才会原子移动到：

```text
data/raw/tushare/trade_date=<交易日>/
```

目标目录或暂存目录已经存在时脚本会直接报错，不会覆盖既有数据。下载失败时
暂存目录会保留，便于检查实际失败现场。

## 运行测试

```powershell
python -m pytest -q
```

根目录的 `pytest.ini` 将测试发现范围限制在 `tests/`，归档的 CSMAR 测试不会
参与当前 Tushare 流程的验证。

## CSMAR 备用快照

备用目录为 `backup/csmar_snapshot_migrated_2026-08-04/`。其中 13 个原始及
合并数据文件共 `3,865,198,842` 字节，文件清单和哈希记录在
`manifest.sha256.csv`。备用数据只读保留，不会被新的 Tushare 流程修改。
