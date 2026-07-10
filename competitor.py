# -*- coding: utf-8 -*-
"""競品錨定：讀 PCHome+MOMO 藍牙耳機競品快照，給每個耳機 SKU 對到
「同形態、相近價位」的市場價（中位、低標），作為漲價天花板與市場定位參考。

限制：目前是「單張快照」，只能做定位錨定（漲價煞車），無法估交叉彈性/權重 w
     （那需要每月連續快照，見 README 的第 2 步）。
"""
import os
import re
import glob


# 我方品牌（算市場中位時要排除，否則等於拿自己錨自己）
OWN_BRANDS = {'JLAB', 'EARFUN', 'CLEER'}


def form_of(name):
    """從品名判斷形態，對齊競品表的分類。"""
    s = str(name)
    if re.search(r'骨傳導|氣傳導', s):
        return '開放/耳掛/骨傳導'
    if re.search(r'開放|耳夾|耳掛|夾式|不入耳|OpenFit|Open ', s, re.I):
        return '開放/耳掛/骨傳導'
    if re.search(r'耳罩|頭戴|罩式|over.?ear', s, re.I):
        return '耳罩式'
    if re.search(r'頸掛|頸帶|neckband', s, re.I):
        return '頸掛式'
    if re.search(r'單耳|商務(?!.*真無線)', s):
        return '單耳商務'
    if re.search(r'真無線|TWS|半入耳|入耳', s, re.I):
        return '真無線'
    return None      # 判不出形態就不錨定


def _load_bq(cfg):
    """從 BigQuery competitor_prices 讀最新一次爬蟲快照。無表/無資料回 None。"""
    import pandas as pd
    try:
        from google.cloud import bigquery
        client = bigquery.Client.from_service_account_json(cfg['bq_key'])
        tbl = cfg.get('bq_competitor', 'igogo-sales-dw.sales.competitor_prices')
        rows = list(client.query(f"""
            SELECT brand, price, form FROM (
              SELECT brand, price, form, scan_date,
                     MAX(scan_date) OVER () AS latest
              FROM `{tbl}` WHERE form IS NOT NULL AND price > 0)
            WHERE scan_date = latest
        """).result())
        if not rows:
            return None
        df = pd.DataFrame([dict(r) for r in rows]).rename(
            columns={'brand': '品牌', 'price': '價格', 'form': '形態'})
        df['own'] = df['品牌'].astype(str).str.upper().isin(OWN_BRANDS)
        return df[~df['own']].reset_index(drop=True)
    except Exception:
        return None


def _load_xlsx(cfg):
    """回退：讀本機 data/competitor 的快照 xlsx。"""
    import pandas as pd
    base = os.path.dirname(os.path.abspath(__file__))
    files = glob.glob(os.path.join(base, 'data', 'competitor', '*.xlsx'))
    if not files:
        return None
    xl = pd.ExcelFile(max(files, key=os.path.getmtime))
    sheet = next((s for s in xl.sheet_names if '競品' in s), xl.sheet_names[0])
    raw = pd.read_excel(xl, sheet, header=None)
    raw.columns = (['品牌', '型號', '價格', '形態', '平台'] + list(raw.columns))[:raw.shape[1]]
    df = raw[pd.to_numeric(raw['價格'], errors='coerce').notna()].copy()
    df['價格'] = df['價格'].astype(float)
    df = df[df['價格'] > 0]
    df['own'] = df['品牌'].astype(str).str.upper().isin(OWN_BRANDS)
    return df[~df['own']].reset_index(drop=True)


def load(cfg):
    """優先 BigQuery 最新爬蟲快照，否則回退本機 xlsx。都沒有回 None。"""
    df = _load_bq(cfg)
    if df is not None and len(df) > 0:
        return df
    return _load_xlsx(cfg)


def build_anchor(cfg):
    """回傳 anchor(form, retail_price) -> dict(median, low, n) 的函式；無競品檔則回 None。"""
    import numpy as np
    df = load(cfg)
    if df is None or len(df) == 0:
        return None
    lo = cfg.get('comp_window_low', 0.65)
    hi = cfg.get('comp_window_high', 1.5)
    min_n = cfg.get('comp_min_n', 5)
    by_form = {form: g['價格'].values for form, g in df.groupby('形態')}

    def anchor(form, price):
        arr = by_form.get(form)
        if arr is None or price is None or price <= 0:
            return None
        near = arr[(arr >= lo * price) & (arr <= hi * price)]
        if len(near) < min_n:      # 相近價帶樣本太少，退回同形態全體
            near = arr
        if len(near) < 3:
            return None
        return dict(median=float(np.median(near)),
                    low=float(np.percentile(near, 25)),
                    n=int(len(near)))
    return anchor


if __name__ == '__main__':
    import sys, io, json
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json'), encoding='utf-8'))
    df = load(cfg)
    print('競品(去我方品牌):', len(df), '筆')
    print('形態分布:', dict(df['形態'].value_counts()))
    anchor = build_anchor(cfg)
    for form, p in [('真無線', 1099), ('真無線', 600), ('開放/耳掛/骨傳導', 1400), ('耳罩式', 2000)]:
        print(f'  {form} @ {p} →', anchor(form, p))
