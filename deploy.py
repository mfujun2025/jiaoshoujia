# -*- coding: utf-8 -*-
"""
脚手架.cn 发布脚本 —— 走 GitHub REST API，不用 git push。

为什么不用 git push：本机装了网络加速工具（Watt Toolkit），git 的网络子进程会被
SIGTERM，push 常常卡死或超时。Git Data API 直传效果等同，且不依赖本地 git 状态。

用法:
    # 1) 只发布站点产物 public/ → gh-pages 分支
    python deploy.py

    # 2) 同时把源码（content/templates/static/构建脚本）推到 main
    python deploy.py --source

    # 3) 指定仓库（默认 mfujun2025/jiaoshoujia）
    python deploy.py --repo mfujun2025/your-repo

    # 4) 仓库不存在时自动创建（public 仓库）
    python deploy.py --create

凭据从 ~/.git-credentials 读取，不写死在脚本里。
"""
import os
import re
import io
import sys
import json
import base64
import argparse
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(ROOT, "public")
API = "https://api.github.com"

DEFAULT_REPO = "mfujun2025/jiaoshoujia"
SITE_BRANCH = "gh-pages"
SRC_BRANCH = "main"

SRC_INCLUDE = ["build.py", "check.py", "deploy.py", "site.json", "categories.json",
               "standards.json", "README.md", "部署说明.md",
               "content", "templates", "static"]
SRC_EXCLUDE_DIRS = {"public", "shots", "__pycache__", ".git", ".workbuddy"}


# --------------------------------------------------------------------------
def read_creds():
    path = os.path.join(os.path.expanduser("~"), ".git-credentials")
    if not os.path.isfile(path):
        raise SystemExit("找不到 %s，无法获取 GitHub 凭据。" % path)
    with io.open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"https://([^:/\s]+):([^@\s]+)@github\.com", line.strip())
            if m:
                return m.group(1), m.group(2)
    raise SystemExit("~/.git-credentials 中没有 github.com 的凭据。")


def api(method, path, token, data=None):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(API + path, data=body, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "scaffold-cn-deploy")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if e.code == 404:
            return {"__status__": 404}
        raise SystemExit("GitHub API %s %s 失败: %s %s\n%s"
                         % (method, path, e.code, e.reason, detail[:500]))


def collect_files(base_dir, includes=None):
    """返回 {相对路径: 绝对路径}。"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(base_dir):
        dirnames[:] = [d for d in dirnames if d not in SRC_EXCLUDE_DIRS]
        for fn in filenames:
            if fn.endswith(".pyc"):
                continue
            # 跳过隐藏文件，但 .nojekyll 必须发布（关闭 GitHub Pages 的 Jekyll 处理）
            if fn.startswith(".") and fn != ".nojekyll":
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, base_dir).replace(os.sep, "/")
            if includes is not None:
                top = rel.split("/")[0]
                if top not in includes:
                    continue
            out[rel] = full
    return out


def blob_sha(token, repo, abspath):
    with open(abspath, "rb") as f:
        content = base64.b64encode(f.read()).decode("ascii")
    res = api("POST", "/repos/%s/git/blobs" % repo, token,
              {"content": content, "encoding": "base64"})
    return res["sha"]


def push_branch(token, repo, branch, files, message, keep_others=False):
    """把 files（{rel: abspath}）作为一个 commit 推到 branch。"""
    entries = []
    for rel, abspath in sorted(files.items()):
        entries.append({
            "path": rel,
            "mode": "100644",
            "type": "blob",
            "sha": blob_sha(token, repo, abspath),
        })
    print("   已上传 %d 个 blob" % len(entries))

    tree_payload = {"tree": entries}
    if keep_others:
        ref = api("GET", "/repos/%s/git/ref/heads/%s" % (repo, branch), token)
        if ref.get("__status__") != 404:
            base = api("GET", "/repos/%s/git/commits/%s" % (repo, ref["object"]["sha"]), token)
            tree_payload["base_tree"] = base["tree"]["sha"]
    tree = api("POST", "/repos/%s/git/trees" % repo, token, tree_payload)

    # 取已有 commit 作为 parent（没有则创建初始提交）
    ref = api("GET", "/repos/%s/git/ref/heads/%s" % (repo, branch), token)
    parents = [] if ref.get("__status__") == 404 else [ref["object"]["sha"]]
    commit_payload = {"message": message, "tree": tree["sha"]}
    if parents:
        commit_payload["parents"] = parents
    commit = api("POST", "/repos/%s/git/commits" % repo, token, commit_payload)

    if parents:
        api("PATCH", "/repos/%s/git/refs/heads/%s" % (repo, branch), token,
            {"sha": commit["sha"]})
    else:
        api("POST", "/repos/%s/git/refs" % repo, token,
            {"ref": "refs/heads/" + branch, "sha": commit["sha"]})
    print("   %s → %s（%s）" % (branch, commit["sha"][:8], message))
    return commit["sha"]


def ensure_repo(token, repo, create):
    if api("GET", "/repos/" + repo, token).get("__status__") != 404:
        return
    if not create:
        raise SystemExit(
            "仓库 %s 不存在。\n"
            "  方案一：在 GitHub 上手动新建一个空仓库\n"
            "  方案二：加 --create 参数，由脚本创建（public 仓库）" % repo)
    owner, name = repo.split("/")
    api("POST", "/user/repos", token,
        {"name": name, "private": False,
         "description": "脚手架.cn — 脚手架施工方案资讯站",
         "auto_init": False})
    print("   已创建仓库 %s" % repo)


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="脚手架.cn 站点发布")
    ap.add_argument("--repo", default=DEFAULT_REPO, help="owner/name，默认 " + DEFAULT_REPO)
    ap.add_argument("--source", action="store_true", help="同时把源码推到 main 分支")
    ap.add_argument("--create", action="store_true", help="仓库不存在时自动创建")
    args = ap.parse_args()

    if not os.path.isdir(PUB):
        raise SystemExit("public/ 不存在，请先运行: python build.py")

    user, token = read_creds()
    print("凭据用户: %s" % user)
    repo = args.repo
    ensure_repo(token, repo, args.create)

    files = collect_files(PUB)
    print("发布站点产物：%d 个文件 → %s" % (len(files), SITE_BRANCH))
    push_branch(token, repo, SITE_BRANCH, files, "发布站点：%d 个文件" % len(files))

    if args.source:
        src = collect_files(ROOT, includes=set(SRC_INCLUDE))
        print("发布源码：%d 个文件 → %s" % (len(src), SRC_BRANCH))
        push_branch(token, repo, SRC_BRANCH, src, "更新源码")

    owner, name = repo.split("/")
    print("=" * 56)
    print("完成。接下来确认两件事：")
    print("  1) 仓库 Settings → Pages：Source 选 Deploy from a branch，")
    print("     分支 %s，目录 /(root)" % SITE_BRANCH)
    print("  2) 域名解析把 xn--kpuo4jd6z.cn 的 CNAME 指向 %s.github.io" % owner)
    print("     或在 Pages 的 Custom domain 填 xn--kpuo4jd6z.cn")
    print("  线上地址: https://%s.github.io/%s/  →  绑定后 https://xn--kpuo4jd6z.cn/"
          % (owner, name))
    print("=" * 56)


if __name__ == "__main__":
    main()
