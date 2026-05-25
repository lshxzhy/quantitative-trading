# Stock Research

这是一个用于股票数据分析的 Python 项目骨架。当前目标是先把项目搭好，后续再逐步接入 CSMAR 的正式数据接口或学校允许的下载方式。

## 重要原则

CSMAR 通常是学校或机构购买授权后使用的数据库。自动化下载前，请确认：

- 你有合法账号和数据访问权限。
- 学校图书馆/数据库使用规则允许通过 API 或程序化方式下载。
- 不做连续批量抓取、绕过验证码、绕过限流、共享账号、转卖数据等行为。

优先路线是使用 CSMAR 官方提供的 Python/API 数据接口；如果只能网页下载，建议先做“人工登录 + 程序整理下载文件”的半自动流程，再确认规则允许后再考虑浏览器自动化。

## 项目结构

```text
stock/
  config/                   # 数据集配置模板
  scripts/                  # Windows 定时任务脚本
  src/stock_pipeline/       # Python 源代码
  tests/                    # 测试
```

`data/`、`logs/`、`state/` 是运行时目录，会由程序按需创建，不提交到 GitHub。

## 第一次本地运行

在 PowerShell 里进入项目目录：

```powershell
cd C:\Users\19029\Desktop\stock
```

当前阶段可以直接使用你电脑上的 Python/Conda 环境运行项目。先确认当前 Python：

```powershell
where python
python --version
```

安装依赖：

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Playwright 还需要安装浏览器运行时：

```powershell
python -m playwright install chromium
python -m playwright --version
```

如果以后希望项目环境和系统环境隔离，也可以改用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

生成本地配置文件：

```powershell
stock-update init
```

检查校园网/CSMAR 是否可达：

```powershell
stock-update check-vpn
```

运行一次数据更新：

```powershell
stock-update update
```

如果你已经在 Windows 里配置好了校园 VPN 连接名，可以在 `.env` 里设置：

```text
VPN_CONNECTION_NAME=你的VPN连接名
```

之后可尝试：

```powershell
stock-update check-vpn --connect-vpn
stock-update update --connect-vpn
```

这个项目不会在代码中保存 VPN 密码或 CSMAR 密码。

## 接入 CSMAR 的下一步

1. 登录学校图书馆的 CSMAR 页面，确认是否有 Python/API 文档。
2. 如果有官方 API，把接口地址、token 或必要参数填入 `.env` 和 `config/datasets.yml`。
3. 如果没有 API，先手动下载一个最小数据集，放入 `data/raw/manual/`，我们再写清洗和入库流程。
4. 每新增一个数据集，都先从“小范围、少字段、短时间区间”测试，确认格式稳定后再扩大。
