# -*- coding: utf-8 -*-
"""脚手架.cn 差量同步 —— 对比远端 tree，只推有差异的文件。"""
import os, re, json, base64, hashlib, urllib.request, sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
API = "https://api.github.com"
REPO = "mfujun2025/jiaoshoujia"

def read_token():
    with open(os.path.expanduser("~/.git-credentials"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r"https://([^:/\s]+):([^@\s]+)@github\.com", line.strip())
            if m:
                return m.group(2)
    raise SystemExit("no token")

def api(method, path, token, data=None):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(API + path, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "scaffold-cn-deploy")
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else {}

def blob_sha_local(path):
    data = open(path, "rb").read()
    h = hashlib.sha1()
    h.update(f"blob {len(data)}\0".encode("ascii") + data)
    return h.hexdigest()

token = read_token()
branch = sys.argv[1] if len(sys.argv) > 1 else "gh-pages"

# Collect local files
if branch == "gh-pages":
    base_dir = os.path.join(ROOT, "public")
else:  # main: source subset
    base_dir = ROOT

files = {}
for dirpath, dirnames, filenames in os.walk(base_dir):
    dirnames[:] = [d for d in dirnames if d not in {"public", "shots", "__pycache__", ".git", ".workbuddy", "node_modules"}]
    for fn in filenames:
        if fn.endswith(".pyc") or (fn.startswith(".") and fn != ".nojekyll"):
            continue
        full = os.path.join(dirpath, fn)
        rel = os.path.relpath(full, base_dir).replace(os.sep, "/")
        if branch == "main":
            top = rel.split("/")[0]
            if top not in {"build.py", "check.py", "deploy.py", "site.json", "categories.json",
                           "standards.json", "README.md", "部署说明.md", "content", "templates", "static",
                           "deploy_sync.py"}:
                continue
        files[rel] = full

# Get remote tree
ref = api("GET", f"/repos/{REPO}/git/ref/heads/{branch}", token)
base_sha = ref["object"]["sha"]
base_commit = api("GET", f"/repos/{REPO}/git/commits/{base_sha}", token)
base_tree_sha = base_commit["tree"]["sha"]
tree = api("GET", f"/repos/{REPO}/git/trees/{base_tree_sha}?recursive=1", token)
remote = {item["path"]: item["sha"] for item in tree.get("tree", []) if item["type"] == "blob"}

print(f"branch={branch} local files={len(files)} remote blobs={len(remote)}")

changed, entries = [], []
for rel, full in sorted(files.items()):
    local_sha = blob_sha_local(full)
    if remote.get(rel) != local_sha:
        data = open(full, "rb").read()
        res = api("POST", f"/repos/{REPO}/git/blobs", token,
                  {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"})
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": res["sha"]})
        changed.append(rel)

print(f"changed files: {len(changed)}")
for c in changed[:50]:
    print("  -", c)
if len(changed) > 50:
    print(f"  ... and {len(changed)-50} more")

if not entries:
    print("Nothing to push.")
    sys.exit(0)

new_tree = api("POST", f"/repos/{REPO}/git/trees", token, {"tree": entries, "base_tree": base_tree_sha})
commit = api("POST", f"/repos/{REPO}/git/commits", token, {
    "message": f"同步更新 {len(changed)} 个文件（{branch}）",
    "tree": new_tree["sha"],
    "parents": [base_sha],
})
api("PATCH", f"/repos/{REPO}/git/refs/heads/{branch}", token, {"sha": commit["sha"]})
print(f"{branch} -> {commit['sha'][:8]} ({len(changed)} files)")
