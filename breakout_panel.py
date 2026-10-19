"""breakout-panel: today's GitHub breakout repos as an animated live-panel page.

Scoring is new-term-radar's breakout signal (MIT); the page is a compact renderer for
live-panel's JSON config format (MIT). Standard library only.

  python breakout_panel.py --demo                 # offline, from fixtures/repos.json
  python breakout_panel.py                        # live GitHub search (GITHUB_TOKEN optional)
  python breakout_panel.py --config panel.json    # render any live-panel config (supported subset)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://api.github.com"
TOP = 15


# --- breakout signal (from zhuyansen/new-term-radar radar/breakout.py) ----------------

def _get(path: str):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "breakout-panel"}
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers), timeout=30) as res:
        return json.load(res)


def repo_term(name: str) -> str:
    return re.sub(r"[-_.]+", " ", name).strip().lower()


def score(repos, before, now, velocity_min=200, delta_min=400):
    """Repos averaging velocity_min stars/day since birth, or up delta_min since the last snapshot."""
    out = []
    for r in repos:
        created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        age = max((now - created).total_seconds() / 86400, 1.0)
        stars = r["stargazers_count"]
        velocity = stars / age
        delta = stars - before[r["full_name"]] if before and r["full_name"] in before else None
        if velocity < velocity_min and (delta is None or delta < delta_min):
            continue
        owner, name = r["full_name"].split("/", 1)
        out.append({"repo": r["full_name"], "owner": owner, "name": name, "stars": stars,
                    "velocity": round(velocity), "delta": delta, "age_days": round(age, 1),
                    "description": (r.get("description") or "")[:120]})
    out.sort(key=lambda x: -max(x["velocity"], x["delta"] or 0))
    return out[:TOP]


def variants(row, display):
    """How people search a repo: 'strata', 'niko1221 strata', 'niko strata'."""
    term = repo_term(row["name"])
    out = [term, f"{row['owner'].lower()} {term}"]
    first = (display or "").split(" ")[0].lower()
    if first and first != row["owner"].lower() and first.isascii() and first.isalpha():
        out.append(f"{first} {term}")
    return out


def search(window_days=14, min_stars=100, pages=2):
    since = (date.today() - timedelta(days=window_days)).isoformat()
    q = urllib.parse.quote(f"created:>={since} stars:>={min_stars}")
    # Pages in parallel; a short page 1 just means page 2 comes back empty.
    with ThreadPoolExecutor(pages) as ex:
        got = ex.map(lambda p: _get(f"/search/repositories?q={q}&sort=stars&order=desc&per_page=100&page={p}"),
                     range(1, pages + 1))
        return [r for g in got for r in g.get("items", [])]


def display_names(owners):
    """Owner display names, fetched in parallel (upstream fetches them one by one)."""
    def one(o):
        try:
            return _get(f"/users/{o}").get("name") or ""
        except OSError:
            return ""
    with ThreadPoolExecutor(8) as ex:
        return dict(zip(owners, ex.map(one, owners)))


# --- live-panel config from breakout rows --------------------------------------------

def panel_config(rows, title="GitHub breakouts", n=6):
    rows = rows[:n]
    W, top, bh, gap = 1200, 300, 150, 24
    cfg = {"meta": {"title": title, "lang": "en"},
           "canvas": {"width": W, "height": top + len(rows) * (bh + gap) + 330, "duration": 12, "preroll": 4},
           "theme": {"preset": "terminal-dark"}, "clock": {"start": "09:00:00", "rate": 1},
           "titlebar": {"text": "~/breakout-panel - " + date.today().isoformat()},
           "credit": {"text": "stars from the GitHub search API; per-second counters extrapolate stars/day"},
           "machines": {"scan": {"type": "lane", "period": 6, "run": 4, "off": 0.5, "busy": "scanning new repos",
                                 "done": ["%d breakouts" % len(rows)],
                                 "log": {"who": "radar", "c": "gr", "msgs": [[f"{r['repo']} {r['velocity']}/day", "up"] for r in rows]
                                         or [["no breakouts today", "ok"]]}}},
           "elements": [{"type": "text", "x": 0, "w": W, "y": 90, "align": "center",
                         "runs": [{"t": title.upper(), "c": "fg", "b": 1}]},
                        {"type": "box", "x": 40, "y": 140, "w": 340, "h": 110, "color": "cy", "pad": [12, 14], "align": "left",
                         "lines": [{"t": "github search", "c": "cy", "b": 1}, {"runs": [{"v": "scan"}]},
                                   {"t": "created < 14 days", "c": "dim"}]}]}
    colors = ["gr", "ye", "pu", "bl", "cy", "gr"]
    for i, r in enumerate(rows):
        y, c, mid = top + i * (bh + gap), colors[i % len(colors)], top + i * (bh + gap) + bh // 2
        cfg["machines"][f"s{i}"] = {"type": "counter", "start": r["stars"], "rate": round(r["velocity"] / 86400, 4),
                                    "format": "comma"}
        gain = f"  +{r['delta']} since last run" if r["delta"] is not None else ""
        cfg["elements"] += [
            {"type": "box", "x": 460, "y": y, "w": 700, "h": bh, "color": c, "pad": [12, 14], "align": "left",
             "lines": [{"t": r["repo"], "c": c, "b": 1}, {"runs": ["stars ", {"v": f"s{i}"}, f"  {r['velocity']}/day{gain}"]},
                       {"t": r["description"][:52] or "-", "c": "dim"}, {"t": " / ".join(r.get("variants", [])), "c": "dim"}]},
            {"type": "flow", "path": [[380, 195], [420, 195], [420, mid], [460, mid]], "period": 1.2 + 0.3 * i,
             "offsets": [0, 0.5], "color": c}]
    cfg["elements"].append({"type": "log", "x": 40, "y": top + len(rows) * (bh + gap) + 20, "w": W - 80, "rows": 5,
                            "title": "log", "cols": [{"key": "time", "x": 0}, {"key": "who", "x": 130},
                                                     {"key": "m", "x": 260}, {"key": "g", "x": 980}]})
    return cfg


# --- compact live-panel renderer: text, box, line, flow, log; counter + lane machines ----

THEME = {"bg": "#14171c", "bar": "#262a32", "line": "#4a5367", "dim": "#6f788c", "fg": "#e4e8f0", "wh": "#ffffff",
         "cy": "#86e1e6", "bl": "#8fb4f6", "gr": "#7fdba8", "pu": "#b9a2f2", "ye": "#e3c07a", "ok": "#7fdba8",
         "warn": "#e3c07a", "bad": "#f08080"}  # live-panel terminal-dark colours

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>live-panel</title><style>
body{margin:0;background:var(--bg);overflow:hidden}#st{position:relative;transform-origin:0 0;font:21px/30px "JetBrains Mono",Consolas,monospace;color:var(--fg)}
#st div{position:absolute;white-space:pre;overflow:hidden}.bx{border:2px solid}.tb{background:var(--bar);font-size:14px;text-align:center}
.tb i{position:absolute;width:14px;height:14px;border-radius:7px}svg{position:absolute;left:0;top:0}
</style></head><body><div id="st"></div><!--LIVE_CONFIG--><script>
var C=JSON.parse(document.getElementById('live-config').textContent),TH=__THEME__,cv=C.canvas||{},P={'4:5':[1200,1500],'3:4':[1080,1440],'1:1':[1080,1080]}[cv.preset]||[1200,1500],
W=cv.width||P[0],H=cv.height||P[1],D=cv.duration||30,PRE=cv.preroll||0,ST=document.getElementById('st'),M=C.machines||{},U=[],FL=[],LOG=null,NS='http://www.w3.org/2000/svg';
for(var k in TH)document.body.style.setProperty('--'+k,TH[k]);ST.style.width=W+'px';ST.style.height=H+'px';document.title=(C.meta||{}).title||'live-panel';
function col(c){return TH[c]||c||TH.fg}
function el(x,y,w,h,cls){var d=document.createElement('div');d.style.cssText='left:'+x+'px;top:'+y+'px;'+(w?'width:'+w+'px;':'')+(h?'height:'+h+'px;':'');if(cls)d.className=cls;ST.appendChild(d);return d}
function lane(m,t){var u=((t-(m.phase||0))%m.period+m.period)%m.period,b=u>=m.off&&u<m.off+m.run,n=Math.floor((t-(m.phase||0)-m.off-m.run)/m.period);
 return b?['|/-\\\\'[Math.floor(t*8)%4]+' '+m.busy,'ye']:['\\u2713 '+m.done[((n%m.done.length)+m.done.length)%m.done.length],'gr']}
function val(id,t){var m=M[id];if(!m)return['{'+id+'}'];if(m.type=='counter'){var v=Math.floor(m.start+m.rate*t);return[(m.prefix||'')+(m.format=='comma'?v.toLocaleString('en-US'):v)+(m.suffix||'')]}
 if(m.type=='lane')return lane(m,t);return['{'+id+'}']}
function runs(d,rs){(Array.isArray(rs)?rs:[rs]).forEach(function(r){var s=document.createElement('span');if(typeof r=='string')r={t:r};if(r.b)s.style.fontWeight=700;
 if(r.v)U.push(function(t){var o=val(r.v,t);s.textContent=o[0];s.style.color=col(r.c||o[1])});else{s.textContent=r.t;s.style.color=col(r.c)}d.appendChild(s)})}
var B={text:function(e){var d=el(e.x||0,e.y-15,e.w,30);d.style.textAlign=e.align||'left';if(e.size)d.style.fontSize=e.size+'px';runs(d,e.runs||{t:e.t||e.text,c:e.c,b:e.b})},
 box:function(e){var d=el(e.x,e.y,e.w,e.h,'bx'),p=e.pad||[12,14];d.style.textAlign=e.align||'center';d.style.borderColor=col(e.color);d.style.boxSizing='border-box';d.style.padding=p[0]+'px '+(p[2]||p[1])+'px 0 '+p[1]+'px';
  if(e.fill)d.style.background=col(e.fill);(e.lines||[]).forEach(function(l){var r=document.createElement('div');r.style.cssText='position:static';
  runs(r,typeof l=='string'?l:(l.runs||{t:l.t,c:l.c,b:l.b}));d.appendChild(r)})},
 line:function(e){var x=Math.min(e.from[0],e.to[0]),y=Math.min(e.from[1],e.to[1]);el(x-1,y-1,Math.abs(e.to[0]-e.from[0])+2,Math.abs(e.to[1]-e.from[1])+2).style.background=col(e.color||'line')},
 flow:function(e){var s=document.createElementNS(NS,'svg'),pl=document.createElementNS(NS,'polyline');s.setAttribute('width',W);s.setAttribute('height',H);
  pl.setAttribute('points',e.path.join(' '));pl.setAttribute('fill','none');pl.setAttribute('stroke',TH.line);pl.setAttribute('stroke-width',2);s.appendChild(pl);
  var segs=[],L=0;for(var i=1;i<e.path.length;i++){var a=e.path[i-1],b=e.path[i],l=Math.hypot(b[0]-a[0],b[1]-a[1]);segs.push([a,b,l]);L+=l}
  var dots=e.offsets.map(function(){var c=document.createElementNS(NS,'circle');c.setAttribute('r',6);c.setAttribute('fill',col(e.color));s.appendChild(c);return c});
  ST.appendChild(s);FL.push(e);U.push(function(t){dots.forEach(function(c,j){var f=(((t+PRE)/e.period+e.offsets[j])%1)*L;
   for(var i=0;i<segs.length;i++){if(f<=segs[i][2]||i==segs.length-1){var q=Math.min(f/segs[i][2],1),a=segs[i][0],b=segs[i][1];c.setAttribute('cx',a[0]+(b[0]-a[0])*q);c.setAttribute('cy',a[1]+(b[1]-a[1])*q);break}f-=segs[i][2]}})})},
 log:function(e){var d=el(e.x,e.y,e.w,(e.rows+1)*30+20,'bx');d.style.borderColor=TH.line;var h=document.createElement('div');h.style.cssText='position:static;color:'+TH.dim;h.textContent=' '+(e.title||'log');d.appendChild(h);
  var rows=[];for(var i=0;i<e.rows;i++){var r=el(0,30+i*30,e.w,30);d.appendChild(r);rows.push(r)}LOG={e:e,rows:rows}}};
function events(t){var ev=[];for(var id in M){var m=M[id];if(m.type!='lane'||!m.log)continue;var t0=(m.phase||0)+m.off+m.run;
 for(var k=-20;t0+k*m.period<=t;k++){var g=m.log.msgs[((k%m.log.msgs.length)+m.log.msgs.length)%m.log.msgs.length];ev.push([t0+k*m.period,m.log.who,g[0],g[1],m.log.c])}}
 return ev.sort(function(a,b){return a[0]-b[0]})}
var ck=(C.clock||{}),c0=(ck.start||'00:00:00').split(':').map(Number);
function clock(s){var x=Math.floor(c0[0]*3600+c0[1]*60+c0[2]+s*(ck.rate||1));x=(x%86400+86400)%86400;return[x/3600|0,(x/60|0)%60,x%60].map(function(n){return('0'+n).slice(-2)}).join(':')}
if(C.titlebar){var tb=el(0,0,W,38,'tb');tb.style.lineHeight='38px';[['#f2645a',13],['#f1bd3c',35],['#55c552',57]].forEach(function(o){var i=document.createElement('i');i.style.cssText='left:'+o[1]+'px;top:12px;background:'+o[0];tb.appendChild(i)});tb.appendChild(document.createTextNode(C.titlebar.text||''))}
(C.elements||[]).forEach(function(e){if(B[e.type])B[e.type](e);else console.warn('live-panel subset: skipping '+e.type)});
if(C.credit)B.text(Object.assign({x:0,w:W,align:'center',y:H-14,size:12,c:'dim'},C.credit));
function fit(){var s=Math.min(innerWidth/W,innerHeight/H);ST.style.transform='scale('+s+')'}fit();addEventListener('resize',fit);
window.seek=function(t){U.forEach(function(f){f(t)});if(LOG){var ev=events(t).slice(-LOG.e.rows),cs=LOG.e.cols;LOG.rows.forEach(function(r,i){var v=ev[i];r.innerHTML='';if(!v)return;
 var cell={time:clock(v[0]),who:v[1],m:v[2],g:v[3]};cs.forEach(function(c){var s=el(c.x+20,0);s.style.position='absolute';s.textContent=cell[c.key];s.style.color=col(c.key=='who'?v[4]:c.key=='g'?v[3]:c.key=='time'?'dim':'fg');r.appendChild(s)})})}};
window.__ready=true;var T0=performance.now()-1000*(+(/[?&]t=([0-9.]+)/.exec(location.search)||[0,0])[1]);(function loop(n){window.seek(((n-T0)/1000)%D);if(!/[?&]manual/.test(location.search))requestAnimationFrame(loop)})(performance.now());
</script></body></html>"""


def render(cfg) -> str:
    blob = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    page = PAGE.replace("__THEME__", json.dumps({**THEME, **(cfg.get("theme") or {}).get("colors", {})}))
    return page.replace("<!--LIVE_CONFIG-->", f'<script id="live-config" type="application/json">{blob}</script>')


def main(argv=None):
    ap = argparse.ArgumentParser(description="GitHub breakout repos as an animated live-panel page.")
    ap.add_argument("--demo", action="store_true", help="offline: score fixtures/repos.json")
    ap.add_argument("--config", help="render this live-panel config instead of fetching breakouts")
    ap.add_argument("--out", default="breakout-panel.html")
    ap.add_argument("--state", help="JSON star snapshot; enables the +N-since-last-run signal")
    ap.add_argument("--window", type=int, default=14)
    ap.add_argument("--min-stars", type=int, default=100)
    ap.add_argument("--json", action="store_true", help="print breakout rows as JSON")
    a = ap.parse_args(argv)
    if a.config:
        cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    else:
        if a.demo:
            fx = json.loads((ROOT / "fixtures" / "repos.json").read_text(encoding="utf-8"))
            repos, now, names = fx["items"], datetime.fromisoformat(fx["now"].replace("Z", "+00:00")), None
        else:
            repos, now, names = search(a.window, a.min_stars), datetime.now(timezone.utc), {}
        before = json.loads(Path(a.state).read_text()) if a.state and Path(a.state).exists() else None
        rows = score(repos, before, now)
        if a.state and repos:
            Path(a.state).write_text(json.dumps({r["full_name"]: r["stargazers_count"] for r in repos}))
        if names is not None:
            names = display_names([r["owner"] for r in rows])
        for r in rows:
            r["variants"] = variants(r, (names or {}).get(r["owner"], ""))
        if a.json:
            print(json.dumps(rows, indent=1))  # ASCII-safe on non-UTF-8 consoles
        for r in rows[:6]:
            print(f"{r['velocity']:>6}/day  {r['stars']:>7,}  {r['repo']}", file=sys.stderr if a.json else sys.stdout)
        cfg = panel_config(rows)
    Path(a.out).write_text(render(cfg), encoding="utf-8")
    print(f"wrote {a.out}", file=sys.stderr if a.json else sys.stdout)


if __name__ == "__main__":
    main()
