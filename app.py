#!/usr/bin/env python3
# Lightspeed Tracker - minimal hourly internet speed tracker
# Copyright (C) 2026 Federico Molinari
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lightspeed Tracker: minimal hourly Ookla speedtest tracker. Stdlib only.

Storage policy:
  - results: raw hourly results, kept for 25h (feeds the 24h chart)
  - daily:   per-day rollups (count, sum, min, max), kept for 31 days
             (feeds the 7-day and 30-day stats; avg is exact via sum/count)

30-day stats = rolling 7-day buckets back from today (last bucket partial),
               avg of weekly avgs, min of weekly mins, max of weekly maxes.
"""
import json
import logging
import os
import sqlite3
import subprocess
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("DISPLAY_TZ", "Europe/Rome"))
DB = os.environ.get("DB_PATH", "/data/lightspeed.db")
PORT = int(os.environ.get("PORT", "8080"))
RUN_MINUTE = int(os.environ.get("RUN_MINUTE", "0"))
SERVER_ID = os.environ.get("SPEEDTEST_SERVER_ID", "").strip()
METRICS = ("down", "up", "ping")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lightspeed")
lock = threading.Lock()


def conn():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    cols = ", ".join(f"{m}_sum REAL, {m}_min REAL, {m}_max REAL" for m in METRICS)
    with closing(conn()) as c, c:
        c.execute("CREATE TABLE IF NOT EXISTS results "
                  "(ts INTEGER PRIMARY KEY, down REAL, up REAL, ping REAL)")
        c.execute(f"CREATE TABLE IF NOT EXISTS daily (day TEXT PRIMARY KEY, n INTEGER, {cols})")


def run_speedtest():
    cmd = ["speedtest", "--accept-license", "--accept-gdpr", "-f", "json"]
    if SERVER_ID:
        cmd += ["-s", SERVER_ID]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    lines = [l for l in p.stdout.splitlines() if l.lstrip().startswith("{")]
    if p.returncode != 0 or not lines:
        raise RuntimeError((p.stderr or p.stdout).strip() or f"exit {p.returncode}")
    r = json.loads(lines[-1])
    return {
        "down": r["download"]["bandwidth"] * 8 / 1e6,  # bytes/s -> Mbps
        "up": r["upload"]["bandwidth"] * 8 / 1e6,
        "ping": r["ping"]["latency"],
    }


def record(ts, res):
    day = datetime.fromtimestamp(ts, TZ).date().isoformat()
    upd = ", ".join(
        f"{m}_sum={m}_sum+excluded.{m}_sum, "
        f"{m}_min=MIN({m}_min, excluded.{m}_min), "
        f"{m}_max=MAX({m}_max, excluded.{m}_max)" for m in METRICS)
    vals = [v for m in METRICS for v in (res[m],) * 3]
    cutoff_day = (datetime.now(TZ).date() - timedelta(days=31)).isoformat()
    with lock, closing(conn()) as c, c:
        c.execute("INSERT OR REPLACE INTO results VALUES (?,?,?,?)",
                  (ts, res["down"], res["up"], res["ping"]))
        c.execute(f"INSERT INTO daily VALUES (?,1,?,?,?,?,?,?,?,?,?) "
                  f"ON CONFLICT(day) DO UPDATE SET n=n+1, {upd}", [day, *vals])
        c.execute("DELETE FROM results WHERE ts < ?", (ts - 25 * 3600,))
        c.execute("DELETE FROM daily WHERE day < ?", (cutoff_day,))


def do_test():
    try:
        res = run_speedtest()
        record(int(time.time()), res)
        log.info("down %.1f Mbps, up %.1f Mbps, ping %.1f ms", res["down"], res["up"], res["ping"])
    except Exception as e:
        log.error("speedtest failed: %s", e)


def scheduler():
    with closing(conn()) as c:
        last = c.execute("SELECT MAX(ts) FROM results").fetchone()[0] or 0
    if time.time() - last > 55 * 60:
        do_test()
    while True:
        now = datetime.now(timezone.utc)  # schedule in UTC: no DST surprises
        nxt = now.replace(minute=RUN_MINUTE, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(hours=1)
        time.sleep((nxt - now).total_seconds())
        do_test()


# ---------- read side ----------

def _agg(rows):
    n = sum(r["n"] for r in rows)
    if not n:
        return None
    return {m: {"avg": sum(r[f"{m}_sum"] for r in rows) / n,
                "min": min(r[f"{m}_min"] for r in rows),
                "max": max(r[f"{m}_max"] for r in rows)} for m in METRICS}


def stats():
    today = datetime.now(TZ).date()
    with closing(conn()) as c:
        rows = {r["day"]: r for r in c.execute("SELECT * FROM daily")}

    def days(a, b):  # days-ago range, inclusive
        keys = ((today - timedelta(days=i)).isoformat() for i in range(a, b + 1))
        return [rows[k] for k in keys if k in rows]

    week = _agg(days(0, 6))
    weeks = [w for w in (_agg(days(s, min(s + 6, 29))) for s in range(0, 30, 7)) if w]
    month = None
    if weeks:
        month = {m: {"avg": sum(w[m]["avg"] for w in weeks) / len(weeks),
                     "min": min(w[m]["min"] for w in weeks),
                     "max": max(w[m]["max"] for w in weeks)} for m in METRICS}
    return {"last7": week, "last30": month, "weeks_in_30": len(weeks)}


def history():
    since = int(time.time()) - 24 * 3600
    with closing(conn()) as c:
        rows = c.execute("SELECT * FROM results WHERE ts > ? ORDER BY ts", (since,)).fetchall()
    out = []
    for r in rows:
        dt = datetime.fromtimestamp(r["ts"], TZ)
        out.append({"label": dt.strftime("%H:%M"), "full": dt.strftime("%a %d/%m %H:%M"),
                    "down": round(r["down"], 1), "up": round(r["up"], 1), "ping": round(r["ping"], 1)})
    return out


def payload():
    return {"tz": str(TZ), "history": history(), **stats()}


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Lightspeed Tracker</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--fg:#1d2330;--mut:#6b7280;--line:#e5e7eb}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--card:#1a1f26;--fg:#e6e8eb;--mut:#9aa3af;--line:#2a313b}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}
main{max-width:960px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 0 2px}.mut{color:var(--mut);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-top:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{padding:6px 4px;text-align:right;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}th{color:var(--mut);font-weight:500}
h2{font-size:15px;margin:0 0 8px}.chart{position:relative;height:300px}
</style></head><body><main>
<h1>Lightspeed Tracker</h1><div class="mut" id="sub"></div>
<div class="card"><h2>Last 24 hours</h2><div class="chart"><canvas id="c"></canvas></div></div>
<div class="grid"><div class="card"><h2>Last 7 days</h2><div id="w"></div></div>
<div class="card"><h2>Last 30 days <span class="mut">(from weekly values)</span></h2><div id="m"></div></div></div>
</main>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const D = __DATA__;
const h = D.history, last = h[h.length - 1];
document.getElementById('sub').textContent = last
  ? `Last test ${last.full} (${D.tz}): ${last.down} ↓ / ${last.up} ↑ Mbps, ${last.ping} ms`
  : 'No results yet, the first test runs at startup.';
function table(s) {
  if (!s) return '<div class="mut">No data yet.</div>';
  const f = v => v.toFixed(1), rows = [['Download (Mbps)','down'],['Upload (Mbps)','up'],['Ping (ms)','ping']];
  return '<table><tr><th></th><th>Avg</th><th>Min</th><th>Max</th></tr>' +
    rows.map(([n,k]) => `<tr><td>${n}</td><td>${f(s[k].avg)}</td><td>${f(s[k].min)}</td><td>${f(s[k].max)}</td></tr>`).join('') +
    '</table>';
}
document.getElementById('w').innerHTML = table(D.last7);
document.getElementById('m').innerHTML = table(D.last30);
if (window.Chart && h.length) new Chart(document.getElementById('c'), {
  type: 'line',
  data: { labels: h.map(r => r.label), datasets: [
    {label:'Download Mbps', data:h.map(r=>r.down), borderColor:'#2f80ed', backgroundColor:'#2f80ed', yAxisID:'y', tension:.25},
    {label:'Upload Mbps', data:h.map(r=>r.up), borderColor:'#27ae60', backgroundColor:'#27ae60', yAxisID:'y', tension:.25},
    {label:'Ping ms', data:h.map(r=>r.ping), borderColor:'#f2994a', backgroundColor:'#f2994a', yAxisID:'y1', borderDash:[4,3], tension:.25}]},
  options: { maintainAspectRatio:false, interaction:{mode:'index', intersect:false},
    plugins:{tooltip:{callbacks:{title:i=>h[i[0].dataIndex].full}}},
    scales:{ y:{beginAtZero:true, title:{display:true,text:'Mbps'}},
             y1:{beginAtZero:true, position:'right', grid:{drawOnChartArea:false}, title:{display:true,text:'ms'}} } }
});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            data = json.dumps(payload()).replace("</", "<\\/")
            self._send(200, PAGE.replace("__DATA__", data), "text/html; charset=utf-8")
        elif path == "/api":
            self._send(200, json.dumps(payload(), indent=2), "application/json")
        elif path == "/healthz":
            self._send(200, "ok", "text/plain")
        else:
            self._send(404, "not found", "text/plain")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    init_db()
    threading.Thread(target=scheduler, daemon=True).start()
    log.info("listening on :%d, tz %s, tests hourly at minute %02d", PORT, TZ, RUN_MINUTE)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
