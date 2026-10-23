# -*- coding: utf-8 -*-
"""静态在线演示站烘焙：把 --demo 控制台打成零后端单文件 index.html。

原理：core/demo 生成确定性合成库 → 走真实 _latest_state/_preview_payload
渲染链取数 → 内嵌为 window.__BAKED__ + fetch() 拦截 shim——
页面 JS 一行不改，离线双击 / GitHub Pages / 任意静态托管即完整可玩。

用法：python docs/demo_build.py        # 产出 docs/site/index.html
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import webui  # noqa: E402
from core.demo import build_demo_db, demo_cfg, demo_health, demo_routes  # noqa: E402
from core.models import Route  # noqa: E402
from wizard import CITY as _wCITY  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "site", "index.html")

SHIM = """
/* ===== 在线演示烘焙层：fetch 拦截 → 内嵌数据（真实控制台这些请求打到本地 API） ===== */
window.__BAKED__=%s;
(function(){const B=window.__BAKED__;
 const J=o=>new Response(JSON.stringify(o),{status:200,
  headers:{'Content-Type':'application/json; charset=utf-8'}});
 window.fetch=function(u,o){u=String(u);
  if(u.indexOf('/api/state')===0)return Promise.resolve(J(B.state));
  if(u.indexOf('/api/health')===0)return Promise.resolve(J(B.health));
  if(u.indexOf('/api/preview')===0)return Promise.resolve(J(B.preview));
  if(u.indexOf('/api/logtail')===0)return Promise.resolve(J(B.logtail));
  if(u.indexOf('/api/config')===0){
   if(o&&String(o.method||'GET').toUpperCase()==='POST')
    return Promise.resolve(J({ok:false,demo:true,
     err:'在线演示为静态站：保存仅在本机真实控制台可用'}));
   return Promise.resolve(J(B.config));}
  if(u.indexOf('/api/login-state')===0)
   return Promise.resolve(J(B.login||{ok:true,plats:{}}));
  if(u.indexOf('/api/trend')===0){
   const q=new URLSearchParams(u.split('?')[1]||'');
   const k=q.get('from')+'|'+q.get('to')+'|'+q.get('date')+'|'+q.get('days');
   return Promise.resolve(J((B.trend||{})[k]
    ||{ok:false,demo:true,err:'该航线此档无烘焙趋势数据'}));
  }
  if(u.indexOf('/api/srx/watch/trend')===0){
   const q=new URLSearchParams(u.split('?')[1]||'');
   const k=q.get('user')+'|'+q.get('id')+'|'+q.get('days');
   return Promise.resolve(J((B.watchTrends||{})[k]
    ||{ok:false,demo:true,err:'该关注航班此档无烘焙历史'}));
  }
  if(u.indexOf('/api/srx/watch')===0){
   if(o&&String(o.method||'GET').toUpperCase()==='POST')
    return Promise.resolve(J({ok:false,demo:true,
     err:'在线演示为静态站：添加/调整关注请在本机控制台使用'}));
   return Promise.resolve(J(B.watch||{ok:true,demo:true,watches:[]}));
  }
  if(u.indexOf('/api/srx/calendar')===0){
   const q=new URLSearchParams(u.split('?')[1]||'');
   const pair=q.get('from')+'|'+q.get('to');
   const C=B.calendar||{},hit=C[pair+'|'+(q.get('date')||'')]||C[pair];
   if(!hit)return Promise.resolve(J({ok:false,demo:true,
    err:'演示库该航线暂无烘焙价带'}));
   const add=(d,n)=>{const a=d.split('-').map(Number);
    const t=new Date(Date.UTC(a[0],a[1]-1,a[2]+n));
    return t.toISOString().slice(0,10)};
   const anchor=q.get('date')||hit.anchor,end=add(anchor,13);
   const out=Object.assign({},hit,{anchor:anchor,
    departure:(hit.departure||[]).filter(x=>x.date>=anchor&&x.date<=end)});
   return Promise.resolve(J(out));
  }
  if(u.indexOf('/api/srx/links')===0){
   const q=new URLSearchParams(u.split('?')[1]||'');
   const pair=q.get('from')+'|'+q.get('to');
   const L=B.links||{};
   return Promise.resolve(J(L[q.get('from')+'|'+q.get('to')+'|'+q.get('date')]
    ||L[pair]||{ok:true,demo:true,links:[]}));
  }
  if(u.indexOf('/api/srx/health')===0){
   const q=new URLSearchParams(u.split('?')[1]||'');
   const pair=q.get('from')+'|'+q.get('to');
   const H=B.srchealth||{};
   return Promise.resolve(J(H[q.get('from')+'|'+q.get('to')+'|'+q.get('date')]
    ||H[pair]||{ok:false,demo:true,err:'演示库该航线暂无字段健康样本'}));
  }
  return Promise.resolve(J({ok:false,demo:true,
   err:'在线演示为静态烘焙页——此操作在真实控制台（本地运行）可用'}));
 };})();
"""


def build():
    db = os.path.join(tempfile.gettempdir(), "ticket_demo_bake.db")
    build_demo_db(db)
    webui._State.cfg = demo_cfg(db)
    webui._State.users = [{
        "name": "演示用户",
        "routes": [Route(
            from_code=r["from"], from_name=r["from_name"],
            to_code=r["to"], to_name=r["to_name"], dates=r["dates"],
            alert_direct=r["alert_direct"],
            alert_transfer=r["alert_transfer"],
            transfer_arrival_max=r["transfer_arrival_max"],
            dep_time_min=r["dep_time_min"], dep_time_max=r["dep_time_max"])
            for r in demo_routes()],
        "platforms": ["qunar", "ctrip", "fliggy", "tongcheng", "tuniu"],
        "notifier": {"dingtalk": {"at_mobile": "138****1234"}},
        "schedule": {"interval_minutes": 15},
    }]
    import main as _m
    webui._State.version = "demo"   # 页脚魔法值:静态演示态不外显版本（恒 V1.0 呈现面零内部 build 号）
    state = webui._latest_state()
    state["demo"] = True
    webui._demo_seed_watches(db, state)
    watch = webui._watch_list("演示用户")
    watch_trends = {}
    for _w in watch.get("watches", []):
        for _days in (2, 7, 30, 90, 180):
            try:
                watch_trends["演示用户|%s|%d" % (_w["id"], _days)] = \
                    webui._watch_trend("演示用户", _w["id"], _days)
            except Exception:
                pass
    # 半年走势三档烘焙（r323 P1-1 姊妹面）：loadTrend 的 query 键
    # from|to|date|days 与 shim 解析侧同构；_trend_payload 走
    # _State.cfg（指向烘焙合成库）取数，flag 档位随 th 烘死
    trend = {}
    for _r in demo_routes():
        for _days in (30, 90, 180):
            trend["%s|%s|%s|%d" % (_r["from"], _r["to"],
                                   _r["dates"][0], _days)] = \
                webui._trend_payload({
                    "from": [_r["from"]], "to": [_r["to"]],
                    "date": [_r["dates"][0]], "days": [str(_days)],
                    "th": [str(_r["alert_direct"] or 0)]})
    # 检索页价带/深链/字段健康同样烘焙：shim 按 14 天窗口切片，
    # 静态站进页即 14 格价带，不再走真实 API 的 demo 兜底错误体。
    calendar, links, srchealth = {}, {}, {}
    for _r in demo_routes():
        _key = _r["from"] + "|" + _r["to"]
        _dt = _r["dates"][0]
        try:
            calendar[_key + "|" + _dt] = webui._srx_calendar_raw(
                _r["from"], _r["to"], _dt, 14, axis="both")
            calendar.setdefault(_key, calendar[_key + "|" + _dt])
        except Exception:
            pass
        try:
            links[_key + "|" + _dt] = webui._srx_links(
                _r["from"], _r["to"], _dt)
            links.setdefault(_key, links[_key + "|" + _dt])
        except Exception:
            pass
        try:
            srchealth[_key + "|" + _dt] = webui._srx_health(
                _r["from"], _r["to"], _dt)
            srchealth.setdefault(_key, srchealth[_key + "|" + _dt])
        except Exception:
            pass
    baked = {
        "state": state,
        "trend": trend,
        "watch": watch,
        "watchTrends": watch_trends,
        "health": demo_health(),
        "calendar": calendar,
        "links": links,
        "srchealth": srchealth,
        "preview": webui._preview_payload(0),
        "logtail": {"ok": True, "demo": True, "lines": [
            "2026-11-05 14:00:00 [INFO] ticket-monitor: ===== 开始一轮扫描（1 用户 / 3 航线） =====",
            "2026-11-05 14:00:17 [INFO] ticket-monitor: [qunar] 2026-11-05 最低价 ￥1850（航班明细 70 条：直飞 44 / 中转 26）",
            "2026-11-05 14:00:45 [INFO] ticket-monitor: ===== 本轮扫描结束 =====",
        ], "plat": "qunar", "ts": "2026-11-05 14:00"},
        "config": webui._demo_config_payload(),
        "login": {"ok": True, "plats": {
            p: {"saved": False, "active": False,
                "stale": False, "pending": False}
            for p in ("qunar", "ctrip", "tongcheng", "tuniu", "fliggy")}},
    }
    shim = SHIM % json.dumps(baked, ensure_ascii=False)
    page = webui._page_html(webui._State.version)
    assert "__PAGEVER__" not in page, "页面代际令牌未替换（横幅会误报）"
    assert "<script>" in page, "PAGE 结构变化，找不到注入点"
    page = page.replace("<script>", "<script>" + shim, 1)
    page = page.replace("<title>机票监控台</title>",
        "<title>机票监控台 · 自托管五渠道价格监控与钉钉推送</title>")
    page = page.replace(
        '<meta name="description" content="自托管多渠道机票价格监控：五渠道明细、达标强提醒、配置全热加载">',
        '<meta name="description" content="可在线试玩的机票价格监控：五平台报价、达标强提醒、'
        '日期模式条与全量配置可视化；支持钉钉/邮件/ntfy/Bark，本机自托管。">'
        '<meta property="og:title" content="机票监控台 · 在线演示">'
        '<meta property="og:description" content="五渠道机票监控、达标强提醒与全量配置可视化。">'
        '<meta property="og:type" content="website">')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print("baked:", OUT, "(%.0f KB)" % (os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    build()
