# -*- coding: utf-8 -*-
"""從 BigQuery 資料倉儲讀銷售與商品主檔。

資料來源：igogo-sales-dw.sales
  - v_sales：全通路每日銷售明細（已帶 brand/category、成本、毛利、金額異常標記）
  - dim_item：商品主檔（brand_name、category_name、in_price 進價、safe_qty 安全庫存）

回傳月彙總（全通路），下游彈性估計與調價邏輯沿用。
"""
import re


COLOR_WORDS = set('''黑色 白色 藍色 綠色 粉色 紅色 紫色 灰色 黃色 棕色 銀色 金色 卡其 迷彩
消光黑 午夜黑 鋼鐵藍 愛麗絲藍 櫻桃紅 馬卡龍粉 丁香紫 雲朵白 鼠尾草灰 淺天藍 暖柔沙 孔雀綠
榛果可可 濃醇摩卡 蜂蜜奶茶 香草拿鐵 草莓牛奶 焦糖瑪奇朵 亮瓷白 銀白色 棕黑色 恆星黑 魅影黑
燕尾藍 月光紫 魅夜紫 珍珠白 石墨黑 玫瑰金 軍綠 深藍 淺藍 粉紅 桃紅 米白 象牙白 太空灰
薄荷綠 珊瑚橘 奶茶色 霧黑 曜石黑 極光白 星空黑 黑 白 藍 綠 紅 紫 灰 黃 粉 棕 銀 金'''.split())


def model_of(name):
    s = re.sub(r'\[.*?\]|\(.*?\)|（.*?）', '', str(name)).strip()
    toks = s.split()
    while toks and toks[-1] in COLOR_WORDS:
        toks.pop()
    return ' '.join(toks) or str(name).strip()


def _client(cfg):
    from google.cloud import bigquery
    return bigquery.Client.from_service_account_json(cfg['bq_key'])


def load_monthly(cfg):
    """回傳 (mo_df, dim_df, allq_df)。
    mo_df   ：電商通路月彙總（定價/毛利/彈性用，對齊 NO_USER1 頁面價經濟）
              item_code, item_name, brand, category, ym(Period[M]), qty, rev, price, model, seg
    dim_df  ：code, name, brand, category, unit_cost, safe_qty
    allq_df ：全通路月銷量（庫存消耗速度用）item_code, ym(Period[M]), qty
    """
    import pandas as pd
    client = _client(cfg)
    months = cfg.get('elasticity_months', 30)

    def query(sql):
        return pd.DataFrame([dict(r) for r in client.query(sql).result()])

    # 定價通路過濾：優先用指定客戶（MOMO+PChome，對齊 15%/10% 抽成假設），
    # 否則退回整個電商通路。
    custs = cfg.get('pricing_customers') or []
    if custs:
        quoted = ', '.join("'" + c.replace("'", "\\'") + "'" for c in custs)
        price_filter = f"v.cust_name IN ({quoted})"
    else:
        price_filter = f"v.channel_name = '{cfg.get('pricing_channel', '電商')}'"

    mo = query(f"""
    SELECT v.item_code,
           ANY_VALUE(v.item_name) item_name,
           ANY_VALUE(d.brand_name) brand,
           ANY_VALUE(d.category_name) category,
           FORMAT_DATE('%Y-%m', v.sale_date) ym,
           SUM(v.qty) qty, SUM(v.pretax) rev
    FROM `{cfg['bq_view']}` v
    LEFT JOIN `{cfg['bq_dim']}` d USING (item_code)
    WHERE v.qty > 0 AND v.pretax > 0 AND NOT v.amt_anomaly
      AND {price_filter}
      AND v.sale_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {months} MONTH)
    GROUP BY v.item_code, ym
    """)
    mo['qty'] = mo['qty'].astype(float)
    mo['rev'] = mo['rev'].astype(float)
    mo = mo[mo['qty'] > 0].copy()
    mo['price'] = mo['rev'] / mo['qty']
    mo = mo[mo['price'] > 0].copy()
    mo['ym'] = pd.PeriodIndex(mo['ym'], freq='M')
    mo['brand'] = mo['brand'].fillna(mo['item_name'].str.split().str[0]).astype(str).str.upper().str.strip()
    mo['category'] = mo['category'].fillna('')
    mo['model'] = mo['item_name'].map(model_of)
    mo['seg'] = mo['brand'] + ('·' + mo['category'].where(mo['category'] != '', '其他'))

    dim = query(f"""
    SELECT item_code code, item_name name, brand_name brand, category_name category,
           in_price unit_cost, safe_qty
    FROM `{cfg['bq_dim']}`
    """)

    # 庫存消耗速度用：全通路月銷量
    allq = query(f"""
    SELECT item_code, FORMAT_DATE('%Y-%m', sale_date) ym, SUM(qty) qty
    FROM `{cfg['bq_view']}`
    WHERE qty > 0 AND NOT amt_anomaly
      AND sale_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {months} MONTH)
    GROUP BY item_code, ym
    """)
    allq['qty'] = allq['qty'].astype(float)
    allq['ym'] = pd.PeriodIndex(allq['ym'], freq='M')
    return mo, dim, allq


def load_inventory(cfg):
    """從 BigQuery v_inventory 讀最新一日全倉庫存。回傳 ({item_code: bal_qty}, snapshot_date)。"""
    client = _client(cfg)
    inv, tbl = cfg['bq_inventory'], cfg['bq_inventory_tbl']
    rows = list(client.query(f"""
        SELECT item_code, bal_qty, snapshot_date
        FROM `{inv}`
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `{tbl}`)
    """).result())
    stock = {r['item_code']: float(r['bal_qty']) for r in rows if r['bal_qty'] is not None}
    snap = rows[0]['snapshot_date'] if rows else None
    return stock, snap


if __name__ == '__main__':
    import sys, io, json, os
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json'), encoding='utf-8'))
    mo, dim, allq = load_monthly(cfg)
    print('電商月彙總:', len(mo), '品項:', mo['item_code'].nunique(),
          '期間:', mo['ym'].min(), '~', mo['ym'].max())
    print('全通路月列:', len(allq), 'dim 品項:', len(dim), '有成本:', (dim['unit_cost'] > 0).sum())
