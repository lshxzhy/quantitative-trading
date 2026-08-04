# CSMAR 归档代码

该归档代码通过西南财经大学 WebVPN 登录 CSMAR，增量更新以下两类日频数据：

1. 全部 A 股的日个股回报率文件；
2. `000001`、`000300`、`000852`、`000905` 的国内指数日行情文件。

## 准备环境

```powershell
python -m pip install -r requirements.txt
```

脚本只使用 Selenium 缓存中与本机 Chrome 同主版本的 ChromeDriver，不会在
运行爬虫时隐式联网下载驱动。若驱动不存在，脚本会立即报出明确错误。

在项目根目录创建 `.env`：

```dotenv
WEBVPN_USERNAME=你的账号
WEBVPN_PASSWORD=你的密码
```

`.env`、浏览器登录状态和数据目录都已被 Git 忽略。

## 更新数据

```powershell
python csmar_download.py
```

脚本固定执行增量更新，不接收数据类型和下载模式参数。它会：

1. 登录 WebVPN 并打开 CSMAR；
2. 等待 CSMAR 机构会话就绪；
3. 更新 `data/raw/stocks/`；
4. 更新 `data/raw/indexes/`；
5. 检查 ZIP 中的字段、日期范围和指数代码。

本地 ZIP 必须按 `1.zip`、`2.zip` 的形式连续维护。脚本根据已有文件中的
最新交易日期确定增量起点；历史文件缺失、命名错误、字段错误、登录异常或
CSMAR 无数据权限时会直接报错，不会静默跳过或自动改为全量下载。

## 合并原始数据

```powershell
python csmar_merge.py
```

该脚本把原始 ZIP 合并为 `data/processed/stocks.csv` 和
`data/processed/indexes.csv`。

## 运行检查

```powershell
python -m unittest test_csmar_download.py -v
```

测试覆盖日期分段、ChromeDriver 版本匹配、ZIP 连号、最新日期解析、字段和
指数代码校验。
