"""Quick write-permission test."""
import json
import requests
from . import bitable_client as bc
from . import config

url = (f"https://open.feishu.cn/open-apis/bitable/v1/apps/"
       f"{config.BITABLE_APP_TOKEN}/tables/{config.BITABLE_VIDEOS_TABLE}/records")
payload = {"fields": {
    "视频ID": "TEST_LOCAL_001",
    "作者":   "@test_local",
    "标题":   "local processor smoke test",
}}
r = requests.post(url, headers=bc._headers(), json=payload, timeout=15).json()
print(json.dumps(r, ensure_ascii=False, indent=2))
