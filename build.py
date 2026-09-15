# -*- coding: utf-8 -*-
"""
脚手架.cn 静态站构建脚本

用法:
    python build.py

扫描 content/*.md（Markdown + YAML 风格 front matter）→ 生成 public/ 下的
首页、资讯列表（分页）、分类页、详情页、搜索页、关于页、404、sitemap.xml、
robots.txt 与搜索索引 search-index.json。

设计约束（来自本机环境）:
  * 不清空 public/ —— 本机 Python 删除操作被路由到回收站，rmtree 会失败；改为覆盖式写入。
  * 模板占位用 {{TOKEN}} + str.replace —— 不用 str.format，避免 CSS 花括号冲突。
"""
import os
import re
import io
import sys
import json
import html as htmllib
import datetime
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")

import markdown

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")
TEMPLATES = os.path.join(ROOT, "templates")
STATIC = os.path.join(ROOT, "static")
OUT = os.path.join(ROOT, "public")

PAGE_SIZE = 12
SITE_URL = "https://xn--kpuo4jd6z.cn"


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def read_text(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def load_json(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def render(tpl, ctx):
    """{{TOKEN}} 占位替换。"""
    out = tpl
    for k, v in ctx.items():
        out = out.replace("{{%s}}" % k, "" if v is None else str(v))
    return out


def strip_md(text):
    """把 Markdown 正文转成用于搜索索引的纯文本。"""
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"[*_`>|#\-]{1,}", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def parse_front_matter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        fm[k.strip()] = v
    return fm, text[m.end():]


MD = markdown.Markdown(extensions=["tables", "fenced_code", "attr_list", "sane_lists"])


def md_to_html(text):
    MD.reset()
    out = MD.convert(text)
    # 表格套一层横向滚动容器，移动端不撑破布局
    out = re.sub(r"(<table>.*?</table>)", r'<div class="table-scroll">\1</div>', out, flags=re.S)
    return out


def cn_len(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text)) + len(re.findall(r"[A-Za-z0-9]+", text))


# --------------------------------------------------------------------------
# 数据加载
# --------------------------------------------------------------------------
site = load_json(os.path.join(ROOT, "site.json"))
cats_cfg = load_json(os.path.join(ROOT, "categories.json"))
CATS = cats_cfg["items"]
CAT_ORDER = cats_cfg["order"]

T_VERSION = read_text(os.path.join(ROOT, "VERSION")).strip() if os.path.exists(
    os.path.join(ROOT, "VERSION")) else str(int(datetime.datetime.now().timestamp()))

LAYOUT = read_text(os.path.join(TEMPLATES, "layout.html"))
T_HOME = read_text(os.path.join(TEMPLATES, "home.html"))
T_LIST = read_text(os.path.join(TEMPLATES, "list.html"))
T_DETAIL = read_text(os.path.join(TEMPLATES, "detail.html"))
T_SEARCH = read_text(os.path.join(TEMPLATES, "search.html"))
T_ABOUT = read_text(os.path.join(TEMPLATES, "about.html"))
T_SITEMAP = read_text(os.path.join(TEMPLATES, "sitemap.html"))
T_STANDARDS = read_text(os.path.join(TEMPLATES, "standards.html"))

STANDARDS = load_json(os.path.join(ROOT, "standards.json"))


def load_posts():
    posts = []
    if not os.path.isdir(CONTENT):
        return posts
    for fn in sorted(os.listdir(CONTENT)):
        if not fn.endswith(".md") or fn.startswith("_"):
            continue
        raw = read_text(os.path.join(CONTENT, fn))
        fm, body = parse_front_matter(raw)
        slug = fm.get("slug") or fn[:-3]
        cat = fm.get("category", "rule")
        if cat not in CATS:
            print("  ! 未知分类 %s（%s），已归入 %s" % (cat, fn, CAT_ORDER[0]))
            cat = CAT_ORDER[0]
        post = {
            "title": fm.get("title", slug),
            "slug": slug,
            "category": cat,
            "category_name": CATS[cat]["name"],
            "date": fm.get("date", "1970-01-01"),
            "updated": fm.get("updated", ""),
            "desc": fm.get("desc", ""),
            "keywords": fm.get("keywords", ""),
            "featured": str(fm.get("featured", "")).lower() in ("true", "yes", "1"),
            "empty_body": False,
        }
        post["html"] = md_to_html(body)
        post["text"] = strip_md(body)
        post["chars"] = cn_len(post["text"])
        post["read_min"] = max(1, int(round(post["chars"] / 350.0)))
        posts.append(post)
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)
    return posts


# --------------------------------------------------------------------------
# 组件
# --------------------------------------------------------------------------
def nav_html(active=""):
    out = []
    for item in site["nav"]:
        cls = ' class="active"' if item["url"] == active else ""
        out.append('<a href="%s"%s>%s</a>' % (item["url"], cls, item["label"]))
    return "".join(out)


def footer_cats_html():
    return "".join(
        '<li><a href="/category/%s/">%s</a></li>' % (s, CATS[s]["name"]) for s in CAT_ORDER
    )


def card_html(p, tokens=None):
    return (
        '<a class="card" href="/news/{slug}/">'
        '<div class="card-top">'
        '<span class="card-tag">{cat}</span>'
        '<span class="card-date">{date}</span>'
        "</div>"
        "<h3>{title}</h3>"
        "<p>{desc}</p>"
        '<div class="card-foot"><span>{kw}</span><span class="card-more">阅读全文 →</span></div>'
        "</a>"
    ).format(
        slug=p["slug"],
        cat=p["category_name"],
        date=p["date"],
        title=htmllib.escape(p["title"]),
        desc=htmllib.escape(p["desc"]),
        kw=htmllib.escape((p["keywords"] or "").split(",")[0]),
    )


def cat_card_html(slug, count):
    c = CATS[slug]
    return (
        '<a class="cat-card" href="/category/{slug}/">'
        '<div class="cat-card-top"><h3>{name}</h3><span class="cat-n">{n} 篇</span></div>'
        "<p>{desc}</p></a>"
    ).format(slug=slug, name=c["name"], n=count, desc=htmllib.escape(c["desc"]))


# --------------------------------------------------------------------------
# 规范标准资料库
# --------------------------------------------------------------------------
def human_size(n):
    if n >= 1048576:
        return "%.1f MB" % (n / 1048576.0)
    if n >= 1024:
        return "%d KB" % int(round(n / 1024.0))
    return "%d B" % n


def std_file_path(it):
    return os.path.join(STATIC, "standards", it["file"])


def std_download_card_html(it):
    """一份文件的下载卡。文件大小现场 stat，避免清单与实物不一致。"""
    p = std_file_path(it)
    size = human_size(os.path.getsize(p)) if os.path.isfile(p) else "—"
    badge = "dl-badge is-self" if it.get("tag") == "本站" else "dl-badge"
    return (
        '<article class="dl-card">'
        '<div class="dl-top">'
        '<span class="dl-code">%s</span>'
        '<span class="%s">%s</span>'
        '<span class="dl-fmt">%s</span>'
        "</div>"
        "<h3>%s</h3>"
        '<p class="dl-note">%s</p>'
        '<div class="dl-meta">'
        "<span><b>规格</b> %s</span>"
        "<span><b>大小</b> %s</span>"
        "<span><b>来源</b> %s</span>"
        "</div>"
        '<div class="dl-foot">'
        '<a class="dl-btn" href="/standards/%s" download>下载 %s</a>'
        "</div>"
        "</article>"
    ) % (
        htmllib.escape(it["code"]), badge, htmllib.escape(it.get("tag", "")),
        htmllib.escape(it["format"]),
        htmllib.escape(it["name"]), htmllib.escape(it["note"]),
        htmllib.escape(it["fmt_note"]), size, htmllib.escape(it["source"]),
        it["file"], htmllib.escape(it["format"]),
    )


def std_groups_html():
    parts = []
    for g in STANDARDS["groups"]:
        cards = "".join(std_download_card_html(it) for it in g["items"])
        parts.append(
            '<section class="std-group">'
            '<h2 class="std-h2">%s</h2>'
            '<p class="std-group-desc">%s</p>'
            '<div class="dl-grid">%s</div></section>'
            % (htmllib.escape(g["title"]), htmllib.escape(g["desc"]), cards)
        )
    return "".join(parts)


def std_related_card_html(item):
    return (
        '<a class="card" href="/news/{s}/">'
        '<div class="card-top"><span class="card-tag">规范标准</span>'
        '<span class="card-date">速查</span></div>'
        "<h3>{t}</h3><p>{d}</p>"
        '<div class="card-foot"><span>规范与政策</span>'
        '<span class="card-more">阅读全文 →</span></div></a>'
    ).format(s=item["slug"], t=htmllib.escape(item["title"]), d=htmllib.escape(item["desc"]))


def std_source_table_html():
    rows = ["| 类型 | 官方渠道 | 说明 |", "|---|---|---|"]
    for s in STANDARDS["sources"]:
        rows.append("| %s | %s | %s |" % (s["kind"], s["channel"], s["note"]))
    return md_to_html("\n".join(rows))


def std_all_files():
    return [it for g in STANDARDS["groups"] for it in g["items"]]



def pager_html(page, total_pages, base):
    if total_pages <= 1:
        return ""
    parts = ['<nav class="pager" aria-label="分页">']

    def url(n):
        return base if n == 1 else "%spage/%d/" % (base, n)

    if page > 1:
        parts.append('<a href="%s">← 上一页</a>' % url(page - 1))

    shown = set()
    for n in range(1, total_pages + 1):
        if n == 1 or n == total_pages or abs(n - page) <= 1:
            shown.add(n)

    last = 0
    for n in sorted(shown):
        if last and n - last > 1:
            parts.append('<span class="gap">…</span>')
        if n == page:
            parts.append('<span class="cur">%d</span>' % n)
        else:
            parts.append('<a href="%s">%d</a>' % (url(n), n))
        last = n

    if page < total_pages:
        parts.append('<a href="%s">下一页 →</a>' % url(page + 1))

    parts.append("</nav>")
    return "".join(parts)


def grouped_rows_html(posts):
    """按年份分组的紧凑列表。"""
    groups = {}
    for p in posts:
        groups.setdefault(p["date"][:4], []).append(p)
    out = []
    for year in sorted(groups.keys(), reverse=True):
        rows = []
        for p in groups[year]:
            rows.append(
                '<li class="list-row">'
                '<time datetime="{d}">{d}</time>'
                '<span class="lr-cat">{c}</span>'
                '<span class="lr-title"><a href="/news/{s}/">{t}</a>'
                '<span class="lr-desc">{de}</span></span>'
                "</li>".format(
                    d=p["date"], c=p["category_name"], s=p["slug"],
                    t=htmllib.escape(p["title"]), de=htmllib.escape(p["desc"]),
                )
            )
        out.append(
            '<section class="year-group"><h2 class="year-title">%s 年</h2>'
            '<ul class="list-rows">%s</ul></section>' % (year, "".join(rows))
        )
    return "".join(out)


# --------------------------------------------------------------------------
# 页面输出
# --------------------------------------------------------------------------
written = []


def emit(rel, content):
    path = os.path.join(OUT, rel.replace("/", os.sep))
    write_text(path, content)
    written.append(rel)


def page(rel, title, desc, keywords, canonical, content, og="website",
         head_extra="", body_extra="", active=""):
    full = render(LAYOUT, {
        "TITLE": title,
        "DESCRIPTION": desc,
        "KEYWORDS": keywords,
        "CANONICAL": canonical,
        "OG_TYPE": og,
        "SITE_NAME": site["name"],
        "SITE_DESCRIPTION": site["description"],
        "NAV": nav_html(active),
        "FOOTER_CATS": footer_cats_html(),
        "YEAR": datetime.date.today().year,
        "CONTENT": content,
        "HEAD_EXTRA": head_extra,
        "BODY_EXTRA": body_extra,
        "ASSET_VER": T_VERSION,
    })
    emit(rel, full)


def out_rel(url_path):
    """把 URL 路径映射到 public 下的文件路径。"""
    p = url_path.strip("/")
    return (p + "/index.html") if p else "index.html"


def main():
    posts = load_posts()
    n_total = len(posts)
    by_cat = {s: [p for p in posts if p["category"] == s] for s in CAT_ORDER}

    print("读取到 %d 篇文章" % n_total)

    # ---------- 首页 ----------
    latest = posts[:6]
    featured = [p for p in posts if p["featured"]][:3]
    feat_block = ""
    if featured:
        feat_block = (
            '<section class="block"><div class="wrap">'
            '<div class="block-head"><h2>重点推荐</h2>'
            '<p>方案编制与规范衔接上最容易出错的地方，优先看这几篇。</p></div>'
            '<div class="card-grid">%s</div></div></section>'
            % "".join(card_html(p) for p in featured)
        )

    home = render(T_HOME, {
        "COUNT": n_total,
        "CAT_COUNT": len(CAT_ORDER),
        "RULE_COUNT": len(by_cat.get("rule", [])),
        "CAT_CARDS": "".join(cat_card_html(s, len(by_cat[s])) for s in CAT_ORDER),
        "FEATURED_BLOCK": feat_block,
        "LATEST_CARDS": "".join(card_html(p) for p in latest),
    })
    page("index.html", "%s — %s" % (site["name"], site["tagline"]),
         site["description"], site["keywords"], SITE_URL + "/", home, active="/")

    # ---------- 资讯列表（分页） ----------
    total_pages = max(1, (n_total + PAGE_SIZE - 1) // PAGE_SIZE)
    for page_no in range(1, total_pages + 1):
        chunk = posts[(page_no - 1) * PAGE_SIZE: page_no * PAGE_SIZE]
        rel = "news/index.html" if page_no == 1 else "news/page/%d/index.html" % page_no
        url = "/news/" if page_no == 1 else "/news/page/%d/" % page_no
        title = "方案资讯" + ("" if page_no == 1 else " · 第 %d 页" % page_no) + " — " + site["name"]
        body = render(T_LIST, {
            "BREADCRUMB": '<a href="/">首页</a><span class="sep">/</span><span>方案资讯</span>',
            "H1": "脚手架施工方案资讯",
            "SUB": "共 %d 篇，按发布时间倒序。可按左侧分类筛选，或用关键词搜索。" % n_total,
            "FILTER_CHIPS": '<a class="chip" href="/news/">全部</a>' + "".join(
                '<a class="chip" href="/category/%s/">%s</a>' % (s, CATS[s]["name"])
                for s in CAT_ORDER
            ),
            "LIST_BODY": grouped_rows_html(chunk),
            "PAGER": pager_html(page_no, total_pages, "/news/"),
        })
        page(rel, title,
             "脚手架施工方案资讯列表，共 %d 篇，涵盖规范标准、专项方案编制、架体选型、安全验收与事故案例。" % n_total,
             site["keywords"], SITE_URL + url, body, active="/news/")

    # ---------- 分类页（分页） ----------
    for slug in CAT_ORDER:
        items = by_cat[slug]
        c = CATS[slug]
        cpages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
        for page_no in range(1, cpages + 1):
            chunk = items[(page_no - 1) * PAGE_SIZE: page_no * PAGE_SIZE]
            rel = ("category/%s/index.html" % slug) if page_no == 1 else (
                "category/%s/page/%d/index.html" % (slug, page_no))
            url = ("/category/%s/" % slug) if page_no == 1 else (
                "/category/%s/page/%d/" % (slug, page_no))
            chips = ['<a class="chip" href="/news/">全部</a>']
            for s in CAT_ORDER:
                on = " on" if s == slug else ""
                chips.append('<a class="chip%s" href="/category/%s/">%s</a>' % (on, s, CATS[s]["name"]))
            body = render(T_LIST, {
                "BREADCRUMB": '<a href="/">首页</a><span class="sep">/</span>'
                              '<a href="/news/">方案资讯</a><span class="sep">/</span><span>%s</span>' % c["name"],
                "H1": c["name"],
                "SUB": htmllib.escape(c["desc"]) + ("（共 %d 篇）" % len(items)),
                "FILTER_CHIPS": "".join(chips),
                "LIST_BODY": grouped_rows_html(chunk) or '<p class="muted">该分类暂无内容。</p>',
                "PAGER": pager_html(page_no, cpages, "/category/%s/" % slug),
            })
            page(rel, "%s — %s" % (c["name"], site["name"]),
                 c["desc"], c["keywords"], SITE_URL + url, body, active="/category/%s/" % slug)

    # ---------- 详情页 ----------
    for p in posts:
        idx = posts.index(p)
        same = [x for x in posts if x["category"] == p["category"] and x["slug"] != p["slug"]][:3]
        if len(same) < 3:
            same += [x for x in posts if x["slug"] != p["slug"] and x not in same][:3 - len(same)]
        related = ""
        if same:
            related = (
                '<section class="related"><h2>相关阅读</h2><div class="card-grid">%s</div></section>'
                % "".join(card_html(x) for x in same)
            )
        tags = "".join(
            '<a class="tag" href="/search/?q=%s">%s</a>' % (
                urllib.parse.quote(k.strip()), htmllib.escape(k.strip()))
            for k in (p["keywords"] or "").split(",") if k.strip()
        )
        ld = json.dumps({
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": p["title"],
            "description": p["desc"],
            "datePublished": p["date"],
            "dateModified": p["updated"] or p["date"],
            "keywords": p["keywords"],
            "author": {"@type": "Organization", "name": site["name"]},
            "publisher": {"@type": "Organization", "name": site["name"]},
            "mainEntityOfPage": {"@type": "WebPage", "@id": "%s/news/%s/" % (SITE_URL, p["slug"])},
        }, ensure_ascii=False)
        body = render(T_DETAIL, {
            "BREADCRUMB":
                '<a href="/">首页</a><span class="sep">/</span>'
                '<a href="/category/%s/">%s</a><span class="sep">/</span><span>正文</span>'
                % (p["category"], p["category_name"]),
            "CATEGORY": p["category"],
            "CATEGORY_NAME": p["category_name"],
            "TITLE": htmllib.escape(p["title"]),
            "DESC": htmllib.escape(p["desc"]),
            "DATE": p["date"],
            "WORD_COUNT": p["chars"],
            "READ_MIN": p["read_min"],
            "BODY": p["html"],
            "TAGS": tags,
            "RELATED": related,
        })
        page("news/%s/index.html" % p["slug"], "%s — %s" % (p["title"], site["name"]),
             p["desc"] or site["description"], p["keywords"] or site["keywords"],
             "%s/news/%s/" % (SITE_URL, p["slug"]), body, og="article",
             head_extra='<script type="application/ld+json">%s</script>' % ld,
             active="/category/%s/" % p["category"])

    # ---------- 搜索页 ----------
    page("search/index.html", "站内搜索 — %s" % site["name"],
         "在脚手架.cn 检索全部方案资讯，支持标题、摘要、关键词与正文内容匹配。",
         site["keywords"], SITE_URL + "/search/",
         render(T_SEARCH, {}), active="/search/")

    # ---------- 关于页 ----------
    page("about/index.html", "关于本站与内容更新方式 — %s" % site["name"],
         "脚手架.cn 的内容范围、板块划分、更新机制与可靠性说明。",
         site["keywords"], SITE_URL + "/about/",
         render(T_ABOUT, {}), active="")

    # ---------- 规范标准资料库（下载中心） ----------
    std_files = std_all_files()
    std_missing = [it["file"] for it in std_files if not os.path.isfile(std_file_path(it))]
    if std_missing:
        raise SystemExit("standards.json 声明的文件缺失：%s" % ", ".join(std_missing))
    std_bytes = sum(os.path.getsize(std_file_path(it)) for it in std_files)
    std_size_label = "%d 份文件 · %s" % (len(std_files), human_size(std_bytes))

    std_body = render(T_STANDARDS, {
        "FILE_COUNT": len(std_files),
        "TOTAL_SIZE": human_size(std_bytes),
        "UPDATED": STANDARDS["updated"],
        "SCOPE_BLOCK": md_to_html("\n\n".join(STANDARDS["scope"])),
        "DOWNLOAD_GROUPS": std_groups_html(),
        "RELATED_CARDS": "".join(std_related_card_html(x) for x in STANDARDS["related"]),
        "SOURCE_TABLE": std_source_table_html(),
        "COPYRIGHT": md_to_html(STANDARDS["copyright"]),
    })
    page("standards/index.html", "脚手架规范标准资料库 · 原文下载 — %s" % site["name"],
         "脚手架规范标准与政策法规文件下载：GB 55023-2022 施工脚手架通用规范、住建部令第 37 号危大工程安全管理规定、建办质 2018-31 / 2021-48 / 2024-63 号文件、建质规 2024-5 号重大事故隐患判定标准、2021 年第 50 号淘汰目录，以及可筛选的规范清单 Excel 台账。全部为公开渠道取得，可直接下载。",
         "脚手架规范下载,GB55023-2022下载,危大工程安全管理规定,建办质2021-48号,建办质2024-63号,淘汰目录,脚手架规范清单Excel,脚手架标准PDF",
         SITE_URL + "/standards/", std_body, active="/standards/")

    # ---------- 网站地图（HTML 版）----------
    # 给访客一页看全站，同时把内链铺开便于搜索引擎抓取。
    def map_list(rows):
        lis = "".join('<li><a href="%s">%s</a><span class="map-meta">%s</span></li>'
                      % (u, htmllib.escape(t), m) for u, t, m in rows)
        return '<ul class="map-list">%s</ul>' % lis

    map_parts = ["<h2>主要页面</h2>"]
    map_parts.append(map_list([
        ("/", "首页", ""),
        ("/standards/", "规范标准资料库（文件下载）", std_size_label),
        ("/news/", "全部方案资讯", "%d 篇" % n_total),
        ("/search/", "站内搜索", ""),
        ("/about/", "关于本站与更新方式", ""),
        ("/sitemap.xml", "sitemap.xml（搜索引擎版）", ""),
    ]))
    map_parts.append("<h2>内容分类</h2>")
    map_parts.append(map_list([("/category/%s/" % s, CATS[s]["name"], "%d 篇" % len(by_cat[s]))
                               for s in CAT_ORDER]))
    for s in CAT_ORDER:
        cp = by_cat[s]
        if not cp:
            continue
        map_parts.append('<h2>%s<span class="map-count">%d 篇</span></h2>'
                         % (CATS[s]["name"], len(cp)))
        map_parts.append(map_list([("/news/%s/" % p["slug"], p["title"], p["date"]) for p in cp]))

    # 页面总数 = 固定页(首页/规范资料库/搜索/关于/地图) + 分类页 + 分页列表页 + 文章页
    total_pages_html = n_total + total_pages + 5 + len(CAT_ORDER)
    page("sitemap/index.html", "网站地图 — %s" % site["name"],
         "脚手架.cn 全部页面与文章的总索引，按分类列出所有脚手架施工方案资讯。",
         site["keywords"], SITE_URL + "/sitemap/",
         render(T_SITEMAP, {"SITEMAP_CONTENT": "".join(map_parts),
                            "TOTAL_PAGES": str(total_pages_html)}),
         active="")

    # ---------- 404 ----------
    nf = ('<div class="wrap nf"><h1>404</h1>'
          "<p>页面不存在或已移动。试试从首页或资讯列表重新进入。</p>"
          '<p><a class="btn" href="/">返回首页</a> '
          '<a class="btn" href="/news/" style="background:#1c6bb0">浏览方案资讯</a></p></div>')
    page("404.html", "页面不存在 — %s" % site["name"], "404",
         "", SITE_URL + "/404.html", nf)

    # ---------- 搜索索引 ----------
    index = [{
        "t": p["title"],
        "s": p["slug"],
        "c": p["category"],
        "cn": p["category_name"],
        "d": p["date"],
        "de": p["desc"],
        "k": p["keywords"],
        "b": p["text"][:1200],
    } for p in posts]
    write_text(os.path.join(OUT, "search-index.json"),
               json.dumps(index, ensure_ascii=False, indent=1))
    written.append("search-index.json")

    # ---------- sitemap ----------
    today = datetime.date.today().isoformat()
    urls = [("/", today, "1.0")]
    urls.append(("/standards/", today, "0.9"))
    urls.append(("/news/", today, "0.9"))
    for page_no in range(2, total_pages + 1):
        urls.append(("/news/page/%d/" % page_no, today, "0.4"))
    urls.append(("/search/", today, "0.3"))
    urls.append(("/about/", today, "0.4"))
    urls.append(("/sitemap/", today, "0.4"))
    for s in CAT_ORDER:
        urls.append(("/category/%s/" % s, today, "0.7"))
    for p in posts:
        urls.append(("/news/%s/" % p["slug"], p["updated"] or p["date"], "0.8"))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod, prio in urls:
        sm.append("  <url><loc>%s%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>"
                  % (SITE_URL, path, lastmod, prio))
    sm.append("</urlset>")
    write_text(os.path.join(OUT, "sitemap.xml"), "\n".join(sm))
    written.append("sitemap.xml")

    # ---------- robots ----------
    write_text(os.path.join(OUT, "robots.txt"),
               "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE_URL)
    written.append("robots.txt")

    # ---------- GitHub Pages：CNAME 与 .nojekyll ----------
    # CNAME 必须由构建产出：deploy.py 每次覆盖式推送 gh-pages，
    # 会删掉 GitHub 后台自动生成的 CNAME 文件，导致自定义域名被解绑。
    write_text(os.path.join(OUT, "CNAME"), SITE_URL.replace("https://", "").rstrip("/") + "\n")
    written.append("CNAME")
    # .nojekyll 关闭 Jekyll 处理，避免下划线开头的资源被忽略、加快构建
    write_text(os.path.join(OUT, ".nojekyll"), "")
    written.append(".nojekyll")

    # ---------- 静态资源 ----------
    import shutil
    for dirpath, _dirnames, filenames in os.walk(STATIC):
        for fn in filenames:
            if fn.startswith("."):
                continue
            src = os.path.join(dirpath, fn)
            dst = os.path.join(OUT, os.path.relpath(src, STATIC))
            d = os.path.dirname(dst)
            if not os.path.isdir(d):
                os.makedirs(d)
            shutil.copyfile(src, dst)
            written.append(os.path.relpath(dst, OUT).replace(os.sep, "/"))

    print("=" * 52)
    print("构建完成：%d 个页面/文件写入 public/" % len(written))
    print("  文章 %d 篇 | 分类 %d 个 | 列表分页 %d 页" % (n_total, len(CAT_ORDER), total_pages))
    for s in CAT_ORDER:
        print("    - %-8s %d 篇" % (CATS[s]["name"], len(by_cat[s])))
    print("=" * 52)


if __name__ == "__main__":
    main()
