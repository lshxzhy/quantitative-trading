# CSMAR 备用数据快照

该目录保存项目原有的 CSMAR 数据。数据于 2026-08-04 从项目的 `data/`
目录迁移到此处，作为切换到 Tushare 数据源前的只读备用快照。

- 原始 ZIP：`raw/stocks/`、`raw/indexes/`
- 原合并结果：`processed/stocks.csv`、`processed/indexes.csv`
- 原爬虫、合并脚本、测试与说明：`code/`
- 原 Selenium 浏览器状态：`state/`（仅本地保留）
- 文件数：13
- 总字节数：3,865,198,842
- 股票数据观察到的最新交易日：2026-05-26
- 指数数据观察到的最新交易日：2026-05-28

`manifest.sha256.csv` 记录每个文件的大小、原修改时间和 SHA-256。恢复或复制
后应重新计算哈希并与清单逐项核对。该目录不参与新的 Tushare 下载流程。
