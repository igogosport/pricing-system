# -*- coding: utf-8 -*-
"""跨機器路徑解析。

專案放在 Google Drive、桌機與筆電共用，但金鑰只在各自本機的
`~/.claude/secrets/`（不同步、不入雲端）。config.json 寫的是桌機絕對路徑，
在別台機器上會找不到，因此這裡做一層 fallback：

  1. config.json 寫的路徑存在 → 直接用
  2. 否則找 `~/.claude/secrets/<同檔名>`
  3. 再否則看環境變數 IGOGO_SECRETS_DIR

這樣同一份程式碼在桌機、筆電都能跑，而金鑰永遠留在本機。
"""
import os


def _candidates(configured):
    name = os.path.basename(str(configured).replace('\\', '/'))
    yield configured
    yield os.path.join(os.path.expanduser('~'), '.claude', 'secrets', name)
    env_dir = os.environ.get('IGOGO_SECRETS_DIR')
    if env_dir:
        yield os.path.join(env_dir, name)


def resolve_secret(configured):
    """回傳第一個實際存在的路徑；都找不到就回原值（讓呼叫端報清楚的錯）。"""
    for p in _candidates(configured):
        if p and os.path.exists(p):
            return p
    return configured


def resolve_config(cfg):
    """就地把 cfg 裡的金鑰路徑換成本機實際存在的位置。"""
    for key in ('secrets_env', 'bq_key'):
        if key in cfg:
            cfg[key] = resolve_secret(cfg[key])
    return cfg


if __name__ == '__main__':
    import sys, io, json
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    base = os.path.dirname(os.path.abspath(__file__))
    cfg = json.load(open(os.path.join(base, 'config.json'), encoding='utf-8'))
    for k in ('secrets_env', 'bq_key'):
        p = resolve_secret(cfg[k])
        print(f'{k}: {p}  {"✓ 找到" if os.path.exists(p) else "✗ 找不到"}')
