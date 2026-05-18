"""Check language distribution of records in Bitable videos table."""
from collections import Counter
import requests
from . import bitable_client as bc
from . import config

API = "https://open.feishu.cn/open-apis"
url = (f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
       f"/tables/{config.BITABLE_VIDEOS_TABLE}/records?page_size=500")
items = []
page_token = None
for _ in range(20):
    params = {"page_size": 500}
    if page_token: params["page_token"] = page_token
    r = requests.get(url.split('?')[0], headers=bc._headers(), params=params, timeout=30).json()
    if r.get("code") != 0: break
    d = r.get("data", {})
    items.extend(d.get("items", []))
    page_token = d.get("page_token")
    if not d.get("has_more"): break

lang_count = Counter()
tag_lang = Counter()
for rec in items:
    f = rec.get("fields", {})
    lang = f.get("语言", "?")
    tag = f.get("匹配标签", "?")
    lang_count[lang] += 1
    if lang == "ja":
        tag_lang[tag] += 1

print(f"Total: {len(items)}")
print("\n=== Language distribution ===")
for lang, n in lang_count.most_common():
    print(f"  {lang:6s}: {n}")

print("\n=== Hashtags producing JA hits ===")
for tag, n in tag_lang.most_common():
    print(f"  #{tag:25s}: {n}")
