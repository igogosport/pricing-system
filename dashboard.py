# -*- coding: utf-8 -*-
"""產出單檔互動儀表板 HTML。由 run_monthly.py 呼叫。"""
import json


def build(records, meta):
    data_json = json.dumps(records, ensure_ascii=False)
    meta_json = json.dumps(meta, ensure_ascii=False)
    return HTML.replace('__DATA__', data_json).replace('__META__', meta_json)


HTML = r'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>調價儀表板</title>
<style>
:root { --bg:#f7f6f3; --card:#fff; --ink:#1a1a1a; --mut:#6b6a66; --line:#e3e2dc;
  --up:#2e7d32; --up-bg:#e6f2e6; --down:#b45309; --down-bg:#fbeee0;
  --bad:#b3261e; --bad-bg:#f9e3e1; --hold:#52514e; --hold-bg:#eeede9; --acc:#185fa5; }
* { box-sizing:border-box; margin:0; }
body { font-family:"Segoe UI","Microsoft JhengHei",sans-serif; background:var(--bg); color:var(--ink); padding:24px; }
h1 { font-size:22px; font-weight:600; }
.sub { color:var(--mut); font-size:13px; margin:4px 0 20px; }
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:16px; }
.kpi { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; cursor:pointer; }
.kpi.active { outline:2px solid var(--acc); }
.kpi .n { font-size:26px; font-weight:600; }
.kpi .t { font-size:13px; color:var(--mut); }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }
.chip { background:var(--card); border:1px solid var(--line); border-radius:999px; padding:4px 12px; font-size:12px; color:var(--mut); }
.chip b { color:var(--ink); }
.bar { display:flex; gap:10px; margin-bottom:12px; flex-wrap:wrap; }
input[type=search], select { padding:8px 10px; border:1px solid var(--line); border-radius:8px; font-size:14px; background:var(--card); }
input[type=search] { flex:1; min-width:220px; }
.wrap { background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:auto; max-height:65vh; }
table { border-collapse:collapse; width:100%; font-size:13px; }
th { position:sticky; top:0; background:#efeeea; text-align:left; padding:8px 10px; cursor:pointer; white-space:nowrap; user-select:none; }
th:hover { background:#e5e4de; }
td { padding:7px 10px; border-top:1px solid var(--line); white-space:nowrap; }
td.name { max-width:340px; overflow:hidden; text-overflow:ellipsis; }
tr:hover td { background:#faf9f6; }
tr { cursor:pointer; }
.tag { padding:2px 8px; border-radius:6px; font-size:12px; font-weight:600; }
.tag.漲價 { color:var(--up); background:var(--up-bg); }
.tag.降價, .tag.降價出清 { color:var(--down); background:var(--down-bg); }
.tag.檢視-負毛利 { color:var(--bad); background:var(--bad-bg); }
.tag.不動, .tag.贈品出清 { color:var(--hold); background:var(--hold-bg); }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.pos { color:var(--up); } .neg { color:var(--bad); }
#panel { position:fixed; right:0; top:0; height:100vh; width:420px; max-width:92vw; background:var(--card);
  border-left:1px solid var(--line); box-shadow:-8px 0 24px rgba(0,0,0,.08); padding:22px; overflow:auto;
  transform:translateX(105%); transition:transform .18s ease; }
#panel.open { transform:none; }
#panel h2 { font-size:16px; margin-bottom:2px; }
#panel .code { color:var(--mut); font-size:12px; margin-bottom:14px; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:14px; }
.cell { background:var(--bg); border-radius:8px; padding:10px; }
.cell .t { font-size:11px; color:var(--mut); }
.cell .n { font-size:17px; font-weight:600; }
.why { font-size:13px; color:var(--mut); background:var(--bg); border-radius:8px; padding:10px; margin-bottom:18px; line-height:1.5; }
.sim h3 { font-size:14px; margin-bottom:8px; }
input[type=range] { width:100%; }
.simout { display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-top:10px; }
#close { float:right; border:none; background:none; font-size:20px; cursor:pointer; color:var(--mut); }
.note { font-size:12px; color:var(--mut); margin-top:14px; line-height:1.5; }
</style>
</head>
<body>
<h1>調價儀表板</h1>
<div class="sub" id="sub"></div>
<div class="kpis" id="kpis"></div>
<div class="chips" id="chips"></div>
<div class="bar">
  <input type="search" id="q" placeholder="搜尋品名或編碼…">
  <select id="fbrand"><option value="">全部品牌</option></select>
  <select id="fsrc"><option value="">全部彈性來源</option><option>品類</option><option>品牌</option><option>預設</option></select>
</div>
<div class="wrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
<div id="panel"></div>
<script>
const DATA = __DATA__;
const META = __META__;
let fDir = '', sortKey = '調幅', sortAsc = false;

document.getElementById('sub').textContent =
  `資料期間 ${META.period}｜本期 ${META.run}｜建議售價 ${META.erp_retail}/${META.n} 來自ERP官方定價｜平台後毛利 ${META.back}%｜單月最大調幅 ±${META.max_step}%` +
  (META.comp_anchored ? `｜耳機漲價受競品中位煞車` : '');

const DIRS = ['漲價','降價','贈品出清','檢視-負毛利','不動'];
function kpis() {
  const el = document.getElementById('kpis');
  el.innerHTML = '';
  const mk = (t, n, dir) => {
    const d = document.createElement('div');
    d.className = 'kpi' + (fDir === dir ? ' active' : '');
    d.innerHTML = `<div class="n">${n}</div><div class="t">${t}</div>`;
    d.onclick = () => { fDir = (fDir === dir ? '' : dir); kpis(); render(); };
    el.appendChild(d);
  };
  mk('全部 SKU', DATA.length, '');
  for (const dir of DIRS) mk(dir, DATA.filter(r => r['方向'] === dir).length, dir);
}
kpis();

const chips = document.getElementById('chips');
for (const [k, v] of Object.entries(META.elasticity))
  chips.insertAdjacentHTML('beforeend', `<div class="chip">${k}：<b>${v}</b></div>`);
chips.insertAdjacentHTML('beforeend', `<div class="chip">估不出者用預設 <b>${META.default_e}</b>（步幅減半）</div>`);

const brands = [...new Set(DATA.map(r => r['品牌']))].sort();
const fb = document.getElementById('fbrand');
for (const b of brands) fb.insertAdjacentHTML('beforeend', `<option>${b}</option>`);

const COLS = [
  ['品項編碼', r => r['品項編碼']],
  ['品項名', r => r['品項名']],
  ['品牌', r => r['品牌']],
  ['方向', r => `<span class="tag ${r['方向']}">${r['方向']}</span>`],
  ['目前售價', r => fmt(r['目前售價']) + (r['售價來源']==='推估' ? '<span style="color:var(--mut)">*</span>' : '')],
  ['建議售價', r => `<b>${fmt(r['建議售價'])}</b>`],
  ['建議供貨價', r => fmt(r['建議供貨價'])],
  ['調幅', r => pct(r['調幅'], true)],
  ['真實毛利率', r => pct(r['真實毛利率'])],
  ['目標毛利率', r => pct(r['目標毛利率'])],
  ['市場中位', r => r['市場中位'] == null ? '<span style="color:var(--mut)">—</span>' : fmt(r['市場中位'])],
  ['vs市場', r => r['vs市場'] == null ? '<span style="color:var(--mut)">—</span>' : pct(r['vs市場'], true)],
  ['彈性', r => r['彈性'].toFixed(2) + `<span style="color:var(--mut)">（${r['彈性來源']}）</span>`],
  ['預期銷量變化', r => pct(r['預期銷量變化'], true)],
];
const fmt = n => n == null ? '' : Math.round(n).toLocaleString();
const pct = (x, sign) => {
  if (x == null) return '';
  const v = (x * 100).toFixed(1) + '%';
  const s = sign && x > 0 ? '+' + v : v;
  const c = sign ? (x > 0.001 ? 'pos' : x < -0.001 ? 'neg' : '') : '';
  return `<span class="${c}">${s}</span>`;
};

const thead = document.querySelector('#tbl thead');
thead.innerHTML = '<tr>' + COLS.map(c =>
  `<th data-k="${c[0]}">${c[0]}<span style="color:var(--mut)" id="s-${c[0]}"></span></th>`).join('') + '</tr>';
thead.querySelectorAll('th').forEach(th => th.onclick = () => {
  const k = th.dataset.k;
  if (sortKey === k) sortAsc = !sortAsc; else { sortKey = k; sortAsc = false; }
  render();
});

function filtered() {
  const q = document.getElementById('q').value.trim().toLowerCase();
  const b = fb.value, src = document.getElementById('fsrc').value;
  let rows = DATA.filter(r =>
    (!fDir || r['方向'] === fDir) &&
    (!b || r['品牌'] === b) &&
    (!src || r['彈性來源'] === src) &&
    (!q || (r['品項名'] + r['品項編碼']).toLowerCase().includes(q)));
  rows.sort((x, y) => {
    const a = x[sortKey], b2 = y[sortKey];
    const r = (typeof a === 'number' && typeof b2 === 'number') ? a - b2 : String(a).localeCompare(String(b2), 'zh-TW');
    return sortAsc ? r : -r;
  });
  return rows;
}

function render() {
  const rows = filtered();
  document.querySelectorAll('th span[id^="s-"]').forEach(s => s.textContent = '');
  const ind = document.getElementById('s-' + sortKey);
  if (ind) ind.textContent = sortAsc ? ' ▲' : ' ▼';
  const tb = document.querySelector('#tbl tbody');
  tb.innerHTML = rows.map((r, i) =>
    `<tr data-i="${DATA.indexOf(r)}">` + COLS.map((c, j) => {
      const cls = j >= 4 && j !== 12 ? 'num' : (j === 1 ? 'name' : '');
      return `<td class="${cls}" ${j === 1 ? `title="${r['品項名']}"` : ''}>${c[1](r)}</td>`;
    }).join('') + '</tr>').join('');
  tb.querySelectorAll('tr').forEach(tr => tr.onclick = () => openPanel(DATA[+tr.dataset.i]));
}
['q', 'fbrand', 'fsrc'].forEach(id => document.getElementById(id).addEventListener('input', render));
render();

function openPanel(r) {
  const p = document.getElementById('panel');
  const E = r['彈性'], R = r['目前售價'], P = r['供貨均價'], C = r['成本'], net0 = r['淨收入'];
  const srcTag = r['售價來源'] === 'ERP' ? 'ERP官方定價' : '推估(缺定價)';
  p.innerHTML = `
    <button id="close" onclick="document.getElementById('panel').classList.remove('open')">✕</button>
    <h2>${r['品項名']}</h2>
    <div class="code">${r['品項編碼']}｜${r['品牌']}｜彈性 ${E.toFixed(2)}（${r['彈性來源']}）</div>
    <div class="grid2">
      <div class="cell"><div class="t">目前售價（${srcTag}）→ 建議售價</div><div class="n">${fmt(R)} → <b>${fmt(r['建議售價'])}</b></div></div>
      <div class="cell"><div class="t">供貨均價 → 建議供貨價</div><div class="n">${fmt(P)} → ${fmt(r['建議供貨價'])}</div></div>
      <div class="cell"><div class="t">淨收入 / 台</div><div class="n">${fmt(net0)}</div></div>
      <div class="cell"><div class="t">成本</div><div class="n">${fmt(C)}</div></div>
      <div class="cell"><div class="t">真實毛利率 → 目標</div><div class="n">${(r['真實毛利率']*100).toFixed(1)}% → ${(r['目標毛利率']*100).toFixed(1)}%</div></div>
      <div class="cell"><div class="t">庫存 / 月均銷量</div><div class="n">${fmt(r['庫存量'])} / ${r['月均銷量']}</div></div>
      ${r['市場中位'] == null ? '' : `<div class="cell" style="grid-column:1/3"><div class="t">同形態競品中位（${r['競品數']}件）· 你的定位</div><div class="n">${fmt(r['市場中位'])}　<span style="font-size:13px;color:${r['vs市場']>0.03?'var(--text-danger)':r['vs市場']<-0.03?'var(--text-success)':'var(--text-secondary)'}">你${r['vs市場']>0?'高':'低'}於市場 ${Math.abs(Math.round(r['vs市場']*100))}%</span></div></div>`}
    </div>
    <div class="why"><span class="tag ${r['方向']}">${r['方向']}</span>　${r['理由']}</div>
    <div class="sim">
      <h3>What-if 試算：如果售價調 <span id="dv">0%</span></h3>
      <input type="range" id="dr" min="-20" max="20" value="0" step="1">
      <div class="simout" style="grid-template-columns:1fr 1fr 1fr 1fr">
        <div class="cell"><div class="t">新建議售價</div><div class="n" id="o0">–</div></div>
        <div class="cell"><div class="t">新供貨價</div><div class="n" id="o1">–</div></div>
        <div class="cell"><div class="t">預期銷量</div><div class="n" id="o2">–</div></div>
        <div class="cell"><div class="t">毛利額變化</div><div class="n" id="o3">–</div></div>
      </div>
      <div class="note">售價與供貨價同比例移動；毛利額＝(淨收入−成本)×銷量。調幅超過 ±10% 時彈性外推參考性下降。</div>
    </div>`;
  const dr = p.querySelector('#dr');
  const upd = () => {
    const d = +dr.value / 100;
    p.querySelector('#dv').textContent = (d > 0 ? '+' : '') + Math.round(d * 100) + '%';
    const q = Math.pow(1 + d, E);
    const g0 = net0 - C, g1 = net0 * (1 + d) - C;
    p.querySelector('#o0').textContent = fmt(Math.round(R * (1 + d) / 10) * 10);
    p.querySelector('#o1').textContent = fmt(P * (1 + d));
    p.querySelector('#o2').textContent = '×' + q.toFixed(2);
    const o3 = p.querySelector('#o3');
    if (g0 <= 0) { o3.textContent = g1 <= 0 ? '仍虧損' : '轉正'; o3.className = 'n'; }
    else {
      const chg = q * g1 / g0 - 1;
      o3.textContent = (chg > 0 ? '+' : '') + Math.round(chg * 100) + '%';
      o3.className = 'n ' + (chg > 0.001 ? 'pos' : chg < -0.001 ? 'neg' : '');
    }
  };
  dr.addEventListener('input', upd); upd();
  p.classList.add('open');
}
</script>
</body>
</html>
'''
