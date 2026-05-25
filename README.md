# Quantitative Trading Learning Project

这是一个从零开始学习 Python 股票数据采集与分析的项目。

当前阶段目标：

1. 学会用 Git/GitHub 管理代码。
2. 学会用 Python 编写最小脚本。
3. 学会用 Playwright 打开 WebVPN 和 CSMAR 页面。
4. 逐步把手动操作改写成可维护的自动化代码。

## 约定

- 代码由自己逐步编写。
- 每次只做一个很小的功能。
- 数据、账号、密码、登录状态、下载文件都不上传 GitHub。
- 遇到报错时，先保存报错信息，再逐步定位。

## 建议目录

后续我们会按需要逐步创建目录。不要提前建太多空文件夹。

第一步可以只创建：

```text
scripts/
```

用来放学习脚本，例如：

```text
scripts/01_open_webvpn.py
```

## Git 日常命令

查看当前状态：

```powershell
git status
```

查看具体改动：

```powershell
git diff
```

提交并同步：

```powershell
git add 文件名
git commit -m "说明这次改了什么"
git push
```

