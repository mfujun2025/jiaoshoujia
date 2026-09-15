# 脚手架.cn

脚手架施工方案资讯站。纯静态站点，Python 构建，GitHub Pages 托管。

线上地址：<https://xn--kpuo4jd6z.cn/>

## 目录结构

```
scaffold-cn-site/
├── content/            文章源文件（Markdown + front matter），内容都在这里
├── templates/          HTML 模板（layout / home / list / detail / search / about）
├── static/             样式与脚本（style.css / app.js / favicon.svg）
├── public/             构建产物，直接部署这一层
├── shots/              本地验证截图
├── site.json           站点级配置（站名、副标题、分页大小等）
├── categories.json     分类定义
├── build.py            构建脚本：content/ → public/
├── check.py            产物自检：内链、占位符、索引一致性
├── deploy.py           发布脚本：走 GitHub REST API 推送
└── 部署说明.md         完整维护手册
```

## 本地构建

依赖 Python 3，需要 `markdown` 包。

```bash
python build.py     # 生成 public/
python check.py     # 自检
python -m http.server 8792 --directory public   # 本地预览
```

> 本地预览固定用 **8792** 端口。8791 上可能有其他遗留服务进程会把请求接走，导致目录式 URL 全部 404。

## 发布上线

```bash
python build.py
python deploy.py --source
```

- 站点产物（`public/`）→ `gh-pages` 分支
- 源码（`content/` `templates/` `static/` 及构建脚本）→ `main` 分支

发布脚本走 GitHub Git Data API，不用 `git push`。本机装了网络加速工具（Watt Toolkit），`git push` 的网络子进程会被 SIGTERM 中断，直传 API 效果等同且不依赖本地 git 状态。

凭据从 `~/.git-credentials` 读取，不写死在脚本里。

## 新增一篇文章

1. 在 `content/` 下新建 `<slug>.md`
2. 按下面的 front matter 格式填写头部
3. 运行 `python build.py`

```markdown
---
title: 文章标题
slug: english-slug
category: rule
date: 2026-09-15
desc: 一句话摘要，用于列表卡片与搜索结果
keywords: 关键词一, 关键词二, 关键词三
author: 脚手架.cn
---

正文……
```

`category` 取值见 `categories.json`：`rule`（法规标准）、`scheme`（专项方案）、`type`（架体类型）、`safe`（安全与验收）、`case`（事故案例）。

运行 `build.py` 会自动重建首页、文章列表、分类页、搜索索引和 sitemap，无需改动模板。

## 内容红线

站内涉及规范编号与数值的内容，发布前必须核实：

1. 规范编号与版本号必须准确，注明现行版本与实施日期
2. 关键数值（搭设高度、分项系数、构造尺寸）必须有明确出处
3. 不编造案例，不虚构统计数据

站内目前多处引用 **GB 55023-2022《施工脚手架通用规范》**（2022-10-01 起全文强制）。该规范已废止 GB 51210、JGJ 130 等一批老规范的强制性条文，引用老规范时必须说明其现行效力。

## 部署状态

- 仓库：`mfujun2025/jiaoshoujia`
- 托管分支：`gh-pages`
- 自定义域名：`xn--kpuo4jd6z.cn`（punycode 形式）
