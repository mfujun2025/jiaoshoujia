# -*- coding: utf-8 -*-
"""构建产物自检：内链完整性 + 关键内容断言。用法: python check.py"""
import os
import re
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(ROOT, "public")

pages = []
for dp, _dn, fns in os.walk(PUB):
    for fn in fns:
        if fn.endswith(".html"):
            pages.append(os.path.join(dp, fn))


def url_to_file(u):
    p = u.strip("/")
    if p == "":
        return os.path.join(PUB, "index.html")
    cand = os.path.join(PUB, p.replace("/", os.sep))
    for c in (cand, cand + ".html", os.path.join(cand, "index.html")):
        if os.path.isfile(c):
            return c
    return None


errors = []
warns = []
links = 0

for pg in pages:
    html = open(pg, encoding="utf-8").read()
    rel = os.path.relpath(pg, PUB).replace(os.sep, "/")

    # 1) 内链检查
    for m in re.finditer(r'(?:href|src)="([^"]+)"', html):
        u = m.group(1)
        if u.startswith(("http://", "https://", "mailto:", "#", "data:", "//", "javascript:")):
            continue
        u = u.split("#")[0].split("?")[0]
        if not u:
            continue
        links += 1
        if url_to_file(u) is None:
            errors.append("死链 %s → %s" % (rel, m.group(1)))

    # 2) 基础结构断言
    if "<title>" not in html:
        errors.append("缺 title: " + rel)
    if 'name="description"' not in html:
        warns.append("缺 description: " + rel)
    if rel != "404.html" and "<h1" not in html:
        errors.append("缺 h1: " + rel)
    # 占位符未被替换
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", html)
    if leftover:
        errors.append("未替换占位符 %s: %s" % (leftover, rel))

# 3) 搜索索引
idx_path = os.path.join(PUB, "search-index.json")
idx = json.load(open(idx_path, encoding="utf-8"))
print("搜索索引条数: %d" % len(idx))
for it in idx:
    if not all(k in it for k in ("t", "s", "c", "cn", "d", "de", "k", "b")):
        errors.append("索引字段缺失: " + it.get("s", "?"))
    if len(it["b"]) < 100:
        warns.append("正文过短: " + it["s"])

# 4) sitemap 与实际文章数比对
sm = open(os.path.join(PUB, "sitemap.xml"), encoding="utf-8").read()
locs = re.findall(r"<loc>(.*?)</loc>", sm)
art_in_sm = [l for l in locs if "/news/" in l and "/news/page/" not in l
             and not l.rstrip("/").endswith("/news")]
print("sitemap URL 总数: %d，其中文章 %d 篇" % (len(locs), len(art_in_sm)))
if len(art_in_sm) != len(idx):
    errors.append("sitemap 文章数(%d) ≠ 索引文章数(%d)" % (len(art_in_sm), len(idx)))

# 5) 首页卡片数
home = open(os.path.join(PUB, "index.html"), encoding="utf-8").read()
print("首页文章卡片: %d 张 | 分类卡: %d 个"
      % (home.count('class="card"'), home.count('class="cat-card"')))
if 'class="card"' not in home:
    errors.append("首页没有文章卡片")

# 6) 分类页是否都生成
for slug in ("rule", "scheme", "type", "safe", "case"):
    p = os.path.join(PUB, "category", slug, "index.html")
    if not os.path.isfile(p):
        errors.append("缺分类页: " + slug)

print("HTML 页面数: %d | 检查内链: %d 条" % (len(pages), links))
print("-" * 52)
if warns:
    print("提示 %d 条:" % len(warns))
    for w in warns[:10]:
        print("  · " + w)
if errors:
    print("发现 %d 个问题:" % len(errors))
    for e in errors[:25]:
        print("  × " + e)
    sys.exit(1)
print("✓ 自检全部通过：无死链、无未替换占位符、索引与 sitemap 一致")
