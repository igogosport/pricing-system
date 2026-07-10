# -*- coding: utf-8 -*-
"""每月競品爬蟲 → BigQuery。

抓 MOMO + PChome 藍牙耳機（各形態關鍵字），正規化品牌/形態，
以當日 scan_date 累積寫入 `igogo-sales-dw.sales.competitor_prices`。
累積數月後即可用 SQL 把「你的價格/銷量 + 競品價格」對齊，估交叉彈性/權重 w。

用法：python crawl_competitors.py
排程：Windows 工作排程器每月 1 號（錯過自動補跑），見 setup_schedule.ps1
"""
import sys, io, os, re, json, time, datetime
import requests
import urllib3
urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
CFG = json.load(open(os.path.join(BASE, 'config.json'), encoding='utf-8'))
import paths
paths.resolve_config(CFG)   # 桌機/筆電共用：金鑰路徑自動找本機 ~/.claude/secrets/
TABLE = 'igogo-sales-dw.sales.competitor_prices'

# 涵蓋各形態的關鍵字（搜尋會回傳相關品，形態最後由品名分類）
KEYWORDS = ['真無線藍牙耳機', 'TWS耳機', '藍牙耳罩耳機', '骨傳導耳機',
            '開放式藍牙耳機', '耳夾式藍牙耳機', '頸掛藍牙耳機', '降噪藍牙耳機']

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

KNOWN_BRANDS = ['JLab', 'EarFun', 'Cleer', 'SONY', 'Apple', 'Anker', 'Soundcore', 'Bose',
                'Nothing', 'JBL', 'Samsung', 'Sennheiser', 'Audio-Technica', 'Philips', 'PHILIPS',
                'Huawei', 'Xiaomi', 'Redmi', 'QCY', 'Marshall', 'Beats', 'Final', 'Monster',
                'Poly', 'Plantronics', 'KINYO', 'TOZO', 'Urbanista', 'Marley', 'Skullcandy',
                'Yamaha', 'Denon', 'Shokz', 'Kaibo', 'Creative', 'Jabra', 'Google', 'OPPO',
                'realme', 'vivo', 'Motorola', 'Panasonic', 'myFirst', 'iClever', 'Tribit']


def brand_of(name, pchome_brand=None):
    if pchome_brand and str(pchome_brand).strip():
        return str(pchome_brand).strip()
    m = re.match(r'^\s*[【\[]([^】\]]+)[】\]]', str(name))   # 【BRAND】
    if m:
        return m.group(1).strip()
    low = str(name).lower()
    for b in KNOWN_BRANDS:
        if b.lower() in low:
            return b
    return '其他'


def form_of(name):
    s = str(name)
    if re.search(r'骨傳導|氣傳導', s):
        return '開放/耳掛/骨傳導'
    if re.search(r'開放|耳夾|耳掛|夾式|不入耳|openfit|open ', s, re.I):
        return '開放/耳掛/骨傳導'
    if re.search(r'耳罩|頭戴|罩式|over.?ear', s, re.I):
        return '耳罩式'
    if re.search(r'頸掛|頸帶|neckband', s, re.I):
        return '頸掛式'
    if re.search(r'單耳|商務', s) and not re.search(r'真無線', s):
        return '單耳商務'
    if re.search(r'真無線|tws|半入耳|入耳', s, re.I):
        return '真無線'
    return None


def scan_momo():
    out = {}
    for kw in KEYWORDS:
        for page in range(1, 11):
            try:
                r = requests.get('https://www.momoshop.com.tw/search/searchShop.jsp',
                                 params={'keyword': kw, 'searchType': 1, 'curPage': page, '_isFuzzy': 0},
                                 headers={'User-Agent': UA, 'Accept-Language': 'zh-TW'},
                                 timeout=20, verify=False)
                prods = []
                for blk in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', r.text, re.S):
                    try:
                        _walk(json.loads(blk.strip()), prods)
                    except Exception:
                        pass
                if not prods:
                    break
                for p in prods:
                    out.setdefault(p['name'][:80], dict(platform='MOMO', **p, keyword=kw))
            except Exception as e:
                print(f'  MOMO {kw} p{page}: {type(e).__name__}')
                break
            time.sleep(0.5)
    return list(out.values())


def _walk(node, out):
    if isinstance(node, dict):
        if node.get('@type') == 'Product':
            offers = node.get('offers', {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = offers.get('price') if isinstance(offers, dict) else None
            name = node.get('name')
            if name and price:
                try:
                    out.append(dict(name=name.strip(), price=float(str(price).replace(',', '')),
                                    source_id=(node.get('url') or '').strip()))
                except Exception:
                    pass
        for v in node.values():
            _walk(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk(v, out)


def scan_pchome():
    out = {}
    for kw in KEYWORDS:
        try:
            first = requests.get('https://ecshweb.pchome.com.tw/search/v4.3/all/results',
                                 params={'q': kw, 'page': 1, 'sort': 'rnk/dc'},
                                 headers={'User-Agent': UA}, timeout=20).json()
        except Exception as e:
            print(f'  PChome {kw}: {type(e).__name__}')
            continue
        for page in range(1, min(first.get('TotalPage', 1), 15) + 1):
            try:
                data = first if page == 1 else requests.get(
                    'https://ecshweb.pchome.com.tw/search/v4.3/all/results',
                    params={'q': kw, 'page': page, 'sort': 'rnk/dc'},
                    headers={'User-Agent': UA}, timeout=20).json()
            except Exception:
                continue
            for p in data.get('Prods', []):
                pid = p.get('Id')
                if pid and pid not in out:
                    out[pid] = dict(platform='PCHOME', name=p.get('Name'),
                                    price=p.get('Price'), source_id=pid,
                                    pchome_brand=p.get('brand'), keyword=kw)
            time.sleep(0.3)
    return list(out.values())


def main():
    scan_date = datetime.date.today().isoformat()
    print(f'競品爬蟲 {scan_date}')
    momo = scan_momo()
    print(f'  MOMO: {len(momo)} 筆')
    pch = scan_pchome()
    print(f'  PChome: {len(pch)} 筆')

    rows = []
    for r in momo + pch:
        price = r.get('price')
        if not price or float(price) <= 0:
            continue
        name = r.get('name') or ''
        rows.append(dict(scan_date=scan_date, platform=r['platform'],
                         brand=brand_of(name, r.get('pchome_brand')), name=name[:200],
                         price=float(price), form=form_of(name),
                         source_id=str(r.get('source_id') or '')[:300], keyword=r['keyword']))
    print(f'  合計有效 {len(rows)} 筆，形態分布:', end=' ')
    from collections import Counter
    print(dict(Counter(x['form'] for x in rows)))

    # 寫入 BigQuery（表不存在則建立，append 累積）
    from google.cloud import bigquery
    client = bigquery.Client.from_service_account_json(CFG['bq_key'])
    schema = [
        bigquery.SchemaField('scan_date', 'DATE'),
        bigquery.SchemaField('platform', 'STRING'),
        bigquery.SchemaField('brand', 'STRING'),
        bigquery.SchemaField('name', 'STRING'),
        bigquery.SchemaField('price', 'FLOAT'),
        bigquery.SchemaField('form', 'STRING'),
        bigquery.SchemaField('source_id', 'STRING'),
        bigquery.SchemaField('keyword', 'STRING'),
    ]
    try:
        client.get_table(TABLE)
    except Exception:
        client.create_table(bigquery.Table(TABLE, schema=schema))
        print(f'  建立新表 {TABLE}')
    # 同一天重跑先刪當天，避免重複
    client.query(f"DELETE FROM `{TABLE}` WHERE scan_date = '{scan_date}'").result()
    job = client.load_table_from_json(
        rows, TABLE, job_config=bigquery.LoadJobConfig(schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND))
    job.result()
    total = list(client.query(f"SELECT COUNT(*) n, COUNT(DISTINCT scan_date) d FROM `{TABLE}`").result())[0]
    print(f'✅ 已寫入 BigQuery，本次 {len(rows)} 筆；表內累積 {total.n} 筆 / {total.d} 個月份')


if __name__ == '__main__':
    main()
