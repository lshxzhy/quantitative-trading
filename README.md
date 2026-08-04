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
  tushare_pipeline.py # 接口调用、校验与原子落盘
tests/
  test_tushare_pipeline.py
```

## 准备环境

```powershell
python -m pip install -r requirements.txt
```

复制 `.env.example` 中的配置项到本地 `.env`，填入在 Tushare 个人中心获取的
Token：

```dotenv
TUSHARE_TOKEN=你的Token
```

`.env`、`data/`、CSMAR 大文件和浏览器状态均已被 Git 忽略。

## 下载一个交易日

```powershell
python src/download.py --date 2026-05-26
```

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
python -m unittest discover -s tests -v
```

## CSMAR 备用快照

备用目录为 `backup/csmar_snapshot_migrated_2026-08-04/`。其中 13 个原始及
合并数据文件共 `3,865,198,842` 字节，文件清单和哈希记录在
`manifest.sha256.csv`。备用数据只读保留，不会被新的 Tushare 流程修改。
