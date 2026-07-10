# -*- coding: utf-8 -*-
"""ECOUNT ERP API 讀取模組。

金鑰從上鎖金庫讀取（config.json 的 secrets_env 指向 igogo.env），
不寫在程式或專案任何檔案裡。

fetch_master() 回傳 { PROD_CD: {'retail': NO_USER1, 'cost': IN_PRICE, 'name': PROD_DES} }
  - retail: 建議售價（維護在自訂欄位 NO_USER1）
  - cost:   品目主檔標準成本 IN_PRICE（庫存移動平均成本另由庫存成本報表提供，較準）
"""
import json, urllib.request, os, time


def _load_env(env_path):
    env = {}
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def _post(url, payload, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _fetch_live(env_path, account, retries):
    env = _load_env(env_path)
    host = env.get('ECOUNT_API_URL', 'https://oapiib.ecount.com/OAPI/V2').split('/OAPI')[0].replace('https://', '').lower()
    suffix = '_' + account if account and account != env.get('ECOUNT_USER_ID') else ''
    creds = dict(
        COM_CODE=env['ECOUNT_COMPANY_CODE'],
        USER_ID=env.get('ECOUNT_USER_ID' + suffix, env['ECOUNT_USER_ID']),
        API_CERT_KEY=env.get('ECOUNT_API_CERT_KEY' + suffix, env['ECOUNT_API_CERT_KEY']),
        LAN_TYPE='zh-TW', ZONE=env.get('ECOUNT_ZONE', 'IB').lower())
    last = None
    for i in range(retries):
        try:
            login = _post(f'https://{host}/OAPI/V2/OAPILogin', creds)
            sid = login['Data']['Datas']['SESSION_ID']
            rows = _post(f'https://{host}/OAPI/V2/InventoryBasic/GetBasicProductsList?SESSION_ID={sid}', {})['Data']['Result']
            out = {}
            for r in rows:
                code = r.get('PROD_CD')
                if not code:
                    continue
                def num(fld):
                    try:
                        return float(r.get(fld) or 0)
                    except (ValueError, TypeError):
                        return 0.0
                out[code] = {'retail': num('NO_USER1'), 'cost': num('IN_PRICE'), 'name': r.get('PROD_DES', '')}
            return out
        except Exception as e:      # 412=登入頻率限制，退避重試
            last = e
            if i < retries - 1:
                time.sleep(15 * (i + 1))
    raise last


def _fetch_stock_live(env_path, account, retries):
    import datetime
    env = _load_env(env_path)
    host = env.get('ECOUNT_API_URL', 'https://oapiib.ecount.com/OAPI/V2').split('/OAPI')[0].replace('https://', '').lower()
    suffix = '_' + account if account and account != env.get('ECOUNT_USER_ID') else ''
    creds = dict(
        COM_CODE=env['ECOUNT_COMPANY_CODE'],
        USER_ID=env.get('ECOUNT_USER_ID' + suffix, env['ECOUNT_USER_ID']),
        API_CERT_KEY=env.get('ECOUNT_API_CERT_KEY' + suffix, env['ECOUNT_API_CERT_KEY']),
        LAN_TYPE='zh-TW', ZONE=env.get('ECOUNT_ZONE', 'IB').lower())
    today = datetime.date.today().strftime('%Y%m%d')
    last = None
    for i in range(retries):
        try:
            login = _post(f'https://{host}/OAPI/V2/OAPILogin', creds)
            sid = login['Data']['Datas']['SESSION_ID']
            r = _post(f'https://{host}/OAPI/V2/InventoryBalance/GetListInventoryBalanceStatus?SESSION_ID={sid}',
                      {'BASE_DATE': today})
            out = {}
            for x in r['Data']['Result']:
                code = x.get('PROD_CD')
                if code:
                    try:
                        out[code] = float(x.get('BAL_QTY') or 0)
                    except (ValueError, TypeError):
                        pass
            return out
        except Exception as e:
            last = e
            if i < retries - 1:
                time.sleep(15 * (i + 1))
    raise last


def fetch_stock(env_path, account='ERIC', cache_path=None, cache_ttl_h=12, retries=3):
    """抓即時總庫存 {PROD_CD: BAL_QTY}。成功更新快取；失敗回退快取。"""
    if cache_path is None:
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'ecount_stock.json')
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < cache_ttl_h:
            try:
                return json.load(open(cache_path, encoding='utf-8')), f'快取({age_h:.0f}h前)'
            except Exception:
                pass
    try:
        out = _fetch_stock_live(env_path, account, retries)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump(out, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)
        return out, 'API即時'
    except Exception as e:
        if os.path.exists(cache_path):
            return json.load(open(cache_path, encoding='utf-8')), f'快取(API失敗:{type(e).__name__})'
        raise


def fetch_master(env_path, account='ERIC', cache_path=None, cache_ttl_h=24, retries=3):
    """抓品目主檔。成功則更新快取；失敗（如 412 頻率限制）時，若有快取則回退。"""
    if cache_path is None:
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'ecount_master.json')
    # 快取夠新就直接用，避免頻繁打 API 觸發 412
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < cache_ttl_h:
            try:
                d = json.load(open(cache_path, encoding='utf-8'))
                return {k: v for k, v in d.items()}, f'快取({age_h:.0f}h前)'
            except Exception:
                pass
    try:
        out = _fetch_live(env_path, account, retries)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump(out, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)
        return out, 'API即時'
    except Exception as e:
        if os.path.exists(cache_path):
            d = json.load(open(cache_path, encoding='utf-8'))
            return d, f'快取(API失敗:{type(e).__name__})'
        raise


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json'), encoding='utf-8'))
    m, src = fetch_master(cfg['secrets_env'])
    have = sum(1 for v in m.values() if v['retail'] > 0)
    print(f'來源 {src}：品項 {len(m)}，其中 {have} 個有建議售價(NO_USER1)')
