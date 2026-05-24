# GitHub 新手步骤

下面按“第一次使用 GitHub”的节奏来做。

## 1. 确认本机有 Git

```powershell
git --version
```

如果提示找不到命令，先安装 Git for Windows：<https://git-scm.com/download/win>

## 2. 设置你的 Git 身份

这一步只需要做一次，名字和邮箱会出现在提交记录里：

```powershell
git config --global user.name "你的英文名或GitHub用户名"
git config --global user.email "你的邮箱"
```

## 3. 初始化本地仓库

在项目目录执行：

```powershell
cd C:\Users\19029\Desktop\stock
git init
git status
```

## 4. 第一次提交

```powershell
git add .
git commit -m "Initial stock research project structure"
```

以后你的日常节奏就是：

```powershell
git status
git add 修改过的文件
git commit -m "说明这次改了什么"
```

## 5. 在 GitHub 创建远程仓库

1. 打开 <https://github.com/new>
2. Repository name 可以填 `stock-research`
3. 先不要勾选 README、.gitignore、license，因为本地已经有文件了
4. 创建仓库后，GitHub 会给你一个远程地址，例如：

```text
https://github.com/你的用户名/stock-research.git
```

## 6. 连接并推送到 GitHub

把下面命令里的地址换成你的仓库地址：

```powershell
git remote add origin https://github.com/你的用户名/stock-research.git
git branch -M main
git push -u origin main
```

以后每次提交后同步到 GitHub：

```powershell
git push
```

## 7. 不要上传的数据

这个项目已经配置了 `.gitignore`，默认不会提交：

- `.env`：本地密钥、token、VPN 配置
- `.venv/`：Python 虚拟环境
- `data/raw/`、`data/processed/`：下载的数据
- `state/`、`logs/`：运行状态和日志

如果 `git status` 里出现了账号、密码、token 或大体量数据文件，先不要提交。

