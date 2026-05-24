# CSMAR 接入计划

## 推荐路线

优先使用 CSMAR 官方 Python/API 数据接口。公开资料显示，部分学校的 CSMAR 服务说明提到支持 Python/R/Stata/MATLAB API，但具体接口、权限和参数通常取决于学校购买的子库和账号权限。

因此第一阶段不要直接写网页爬虫，而是先确认：

1. 你所在学校是否购买了目标子库。
2. 学校图书馆页面是否有 CSMAR API 文档。
3. 是否允许程序化下载，以及是否有频率、字段、时间范围限制。
4. 是否可以用 token/API key，而不是网页账号密码。

## 当前代码已经准备好的部分

- `.env`：保存本机配置，不上传 GitHub。
- `stock-update check-vpn`：检查 CSMAR 页面是否可访问。
- `stock-update update`：按 `config/datasets.yml` 执行启用的数据集下载。
- `scripts/setup_windows_task.ps1`：注册每天运行一次的 Windows 定时任务。

## 你拿到 API 文档后需要填写

`.env`：

```text
CSMAR_API_BASE_URL=https://官方接口根地址
CSMAR_API_TOKEN=你的token
```

`config/datasets.yml`：

```yaml
datasets:
  - name: stock_daily
    enabled: true
    method: GET
    endpoint: "/官方接口路径"
    params:
      start_date: "{last_success_date}"
      end_date: "{today}"
    output: "stock_daily_{today}.csv"
```

## 如果学校只支持网页导出

先不要急着全自动爬页面。更稳妥的顺序是：

1. 手动登录 CSMAR，选择一个很小的数据集导出 CSV。
2. 把文件放到 `data/raw/manual/`。
3. 写 Python 清洗脚本，把 CSV 转成统一格式。
4. 确认学校规则允许后，再考虑浏览器自动化。

如果页面有验证码、短信、人机验证或明确禁止批量下载，就不要写绕过逻辑。

