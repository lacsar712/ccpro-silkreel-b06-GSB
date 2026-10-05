import { render } from "preact";
import { useEffect, useMemo, useState } from "preact/hooks";
import { api, clearToken, setToken, token } from "./api.js";
import "./app.css";

const STATUS_LABEL = { soaking: "浸茧", reeling: "缫丝中", reeled: "已缫完" };

// dataviz 校验过的分类色固定槽位：颜色跟随操作人，筛选改变不重排。
const SERIES_COLORS = [
  "#2a78d6",
  "#eb6834",
  "#1baf7a",
  "#eda100",
  "#e87ba4",
  "#008300",
  "#4a3aa7",
  "#e34948",
];
const OTHER_COLOR = "#898781";

function seriesColor(name, allOperators) {
  const i = allOperators.indexOf(name);
  return i >= 0 && i < SERIES_COLORS.length ? SERIES_COLORS[i] : OTHER_COLOR;
}

function fmtTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso || "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function Login({ onOk }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("123456");
  const [err, setErr] = useState("");
  async function submit(e) {
    e.preventDefault();
    setErr("");
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setToken(data.access_token);
      onOk(data.user.role);
    } catch (ex) {
      setErr(ex.message);
    }
  }
  return (
    <div class="login">
      <h1>江口缫丝坞</h1>
      <p>汤温环盆作业台，不是列表台账。</p>
      <form onSubmit={submit} autocomplete="off">
        <label>
          用户名
          <input name="username" autocomplete="off" value={username} onInput={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          密码
          <input name="password" type="password" autocomplete="off" value={password} onInput={(e) => setPassword(e.target.value)} />
        </label>
        <p class="hint">已预填 admin / 123456，另有 worker / 123456、admin2 / 123456</p>
        <button type="submit">登录</button>
      </form>
      {err && <p class="err">{err}</p>}
    </div>
  );
}

export function TopNav({ view, setView, role }) {
  return (
    <nav class="topnav">
      <button class={view === "yard" ? "navbtn active" : "navbtn"} onClick={() => setView("yard")}>
        环盆作业台
      </button>
      {role === "admin" && (
        <button
          class={view === "filter" ? "navbtn active" : "navbtn"}
          onClick={() => setView("filter")}
        >
          采样人过滤
        </button>
      )}
      <span class="navspacer" />
      <button
        class="navbtn"
        onClick={() => {
          clearToken();
          location.reload();
        }}
      >
        退出
      </button>
    </nav>
  );
}

export function TemperatureProfile({ data }) {
  const [hover, setHover] = useState(null);
  const points = data.points;

  const subtitle = !data.configured
    ? "尚未保存过筛选，温谱显示全员汤温"
    : data.operators.length === 0
      ? "一个采样人都没勾选，温谱为空"
      : `按采样人过滤：${data.operators.join("、")}`;

  const groups = useMemo(() => {
    const map = new Map();
    for (const p of points) {
      if (!map.has(p.operator)) map.set(p.operator, []);
      map.get(p.operator).push(p);
    }
    for (const list of map.values()) {
      list.sort((a, b) => Date.parse(a.takenAt) - Date.parse(b.takenAt));
    }
    return (data.allOperators || [])
      .filter((name) => map.has(name))
      .map((name) => ({ name, list: map.get(name) }));
  }, [points, data.allOperators]);

  if (!points.length) {
    // 空表：只画说明，不放假点、不放假线。
    return (
      <section class="card viz-card">
        <h2>汤温温谱</h2>
        <p class="viz-sub">{subtitle}</p>
        <div class="viz-empty">暂无汤温数据点</div>
      </section>
    );
  }

  const W = 720;
  const H = 320;
  const M = { t: 20, r: 28, b: 38, l: 52 };
  const times = points.map((p) => Date.parse(p.takenAt));
  let t0 = Math.min(...times);
  let t1 = Math.max(...times);
  if (t0 === t1) {
    t0 -= 3600_000;
    t1 += 3600_000;
  } else {
    const pad = (t1 - t0) * 0.08;
    t0 -= pad;
    t1 += pad;
  }
  const temps = points.map((p) => p.waterTempC);
  let y0 = Math.min(38, ...temps) - 1;
  let y1 = Math.max(42, ...temps) + 1;
  y0 = Math.floor(y0);
  y1 = Math.ceil(y1);

  const x = (t) => M.l + ((t - t0) / (t1 - t0)) * (W - M.l - M.r);
  const y = (v) => H - M.b - ((v - y0) / (y1 - y0)) * (H - M.t - M.b);

  const yTicks = [];
  for (let v = y0; v <= y1; v += 1) yTicks.push(v);
  const xTicks = [];
  const tickCount = 4;
  for (let i = 0; i <= tickCount; i++) {
    const t = t0 + ((t1 - t0) * i) / tickCount;
    xTicks.push(t);
  }

  return (
    <section class="card viz-card">
      <h2>汤温温谱</h2>
      <p class="viz-sub">{subtitle}</p>
      <div class="viz-root">
        <ul class="legend">
          {groups.map((g) => (
            <li key={g.name}>
              <span class="legendkey" style={{ "--c": seriesColor(g.name, data.allOperators) }} />
              {g.name}
              <em>{g.list.length}</em>
            </li>
          ))}
        </ul>
        <div class="svg-wrap">
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="按采样人分色的汤温时间温谱">
            {/* 38～42℃ 可标已缫完区间 */}
            <rect
              x={M.l}
              y={y(42)}
              width={W - M.l - M.r}
              height={Math.max(0, y(38) - y(42))}
              class="band"
            />
            {yTicks.map((v) => (
              <g key={v}>
                <line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} class="grid" />
                <text x={M.l - 8} y={y(v) + 4} class="axis" text-anchor="end">
                  {v}
                </text>
              </g>
            ))}
            {xTicks.map((t, i) => (
              <text key={i} x={x(t)} y={H - M.b + 20} class="axis" text-anchor="middle">
                {fmtTime(new Date(t).toISOString())}
              </text>
            ))}
            <line x1={M.l} x2={M.l} y1={M.t} y2={H - M.b} class="axisline" />
            <line x1={M.l} x2={W - M.r} y1={H - M.b} y2={H - M.b} class="axisline" />
            <text x={W - M.r} y={y(40) - 6} class="bandlabel" text-anchor="end">
              38～42℃ 可标已缫完
            </text>
            {groups.map((g) => {
              const color = seriesColor(g.name, data.allOperators);
              const d = g.list
                .map((p, i) => `${i === 0 ? "M" : "L"}${x(Date.parse(p.takenAt))},${y(p.waterTempC)}`)
                .join(" ");
              return (
                <g key={g.name}>
                  <path d={d} fill="none" stroke={color} stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                  {g.list.map((p) => {
                    const cx = x(Date.parse(p.takenAt));
                    const cy = y(p.waterTempC);
                    return (
                      <g
                        key={p.id}
                        onMouseEnter={() => setHover({ cx, cy, p, color })}
                        onMouseLeave={() => setHover(null)}
                      >
                        <circle cx={cx} cy={cy} r="12" fill="transparent" />
                        <circle cx={cx} cy={cy} r="4.5" fill={color} stroke="#fcfcfb" stroke-width="2" />
                      </g>
                    );
                  })}
                </g>
              );
            })}
            {hover && <line x1={hover.cx} x2={hover.cx} y1={M.t} y2={H - M.b} class="crosshair" />}
          </svg>
          {hover && (
            <div
              class="tooltip"
              style={{
                left: `${(hover.cx / W) * 100}%`,
                top: `${(hover.cy / H) * 100}%`,
              }}
            >
              <strong>{hover.p.operator}</strong>
              <span>
                {hover.p.basinCode} · {hover.p.waterTempC}℃
              </span>
              <span>{fmtTime(hover.p.takenAt)}</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

export function ReadingsLedger({ data }) {
  const note = !data.configured
    ? "尚未保存过筛选，台账显示全员记录"
    : data.operators.length === 0
      ? "一个采样人都没勾选，台账为空"
      : `与温谱同一批勾选：${data.operators.join("、")}`;
  return (
    <section class="card ledger-card">
      <h2>温谱台账</h2>
      <p class="viz-sub">{note}</p>
      <table class="ledger">
        <thead>
          <tr>
            <th>时间</th>
            <th>盆号</th>
            <th>采样人</th>
            <th class="num">汤温 (℃)</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.id}>
              <td>{fmtTime(r.takenAt)}</td>
              <td>{r.basinCode}</td>
              <td>{r.operator}</td>
              <td class="num">{r.waterTempC}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!data.rows.length && <p class="viz-empty">台账无记录</p>}
    </section>
  );
}

export function Yard({ active }) {
  const [board, setBoard] = useState(null);
  const [profile, setProfile] = useState(null);
  const [ledger, setLedger] = useState(null);
  const [picked, setPicked] = useState(null);
  const [temp, setTemp] = useState("40");
  const [err, setErr] = useState("");

  async function refresh() {
    const [b, p, l] = await Promise.all([
      api("/api/board"),
      api("/api/temperature-profile"),
      api("/api/readings/ledger"),
    ]);
    setBoard(b);
    setProfile(p);
    setLedger(l);
    setPicked((cur) =>
      cur ? b.basins.find((basin) => basin.id === cur.id) || cur : cur
    );
  }

  useEffect(() => {
    if (active) {
      refresh().catch((e) => setErr(e.message));
    }
  }, [active]);

  if (!board) {
    return <div class="yard">{err || "装载环盆…"}</div>;
  }

  const n = board.basins.length;
  async function writeTemp() {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/readings`, {
        method: "POST",
        body: JSON.stringify({ waterTempC: Number(temp) }),
      });
      await refresh();
      setPicked(row);
    } catch (ex) {
      setErr(ex.message);
    }
  }
  async function setStatus(status) {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      await refresh();
      setPicked(row);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  return (
    <div class="yard">
      <div class="topbar">
        <div>
          <h1>{board.filature}</h1>
          <p>{board.riverside} · 点盆登记汤温；已缫完须最近汤温 38～42℃</p>
        </div>
      </div>
      <div class="ring">
        {board.basins.map((b, i) => {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          const left = 50 + Math.cos(angle) * 38;
          const top = 50 + Math.sin(angle) * 38;
          return (
            <button
              key={b.id}
              class={`basin ${b.status}`}
              style={{ left: `${left}%`, top: `${top}%` }}
              onClick={() => setPicked(b)}
            >
              <strong>{b.code}</strong>
              <span>{STATUS_LABEL[b.status]}</span>
            </button>
          );
        })}
      </div>
      {picked && (
        <div class="drawer">
          <h3>
            {picked.code} · {STATUS_LABEL[picked.status]}
          </h3>
          <p>最近汤温：{picked.latestTempC ?? "无"} ℃ · 记录 {picked.readingCount} 次</p>
          <input value={temp} onInput={(e) => setTemp(e.target.value)} />
          <button onClick={writeTemp}>登记汤温</button>
          <div>
            <button onClick={() => setStatus("soaking")}>浸茧</button>
            <button onClick={() => setStatus("reeling")}>缫丝中</button>
            <button onClick={() => setStatus("reeled")}>已缫完</button>
          </div>
          {err && <p class="err">{err}</p>}
        </div>
      )}

      {profile && <TemperatureProfile data={profile} />}
      {ledger && <ReadingsLedger data={ledger} />}
    </div>
  );
}

export function FilterPage({ onSaved }) {
  const [candidates, setCandidates] = useState([]);
  const [picked, setPicked] = useState(null);
  const [version, setVersion] = useState(0);
  const [configured, setConfigured] = useState(false);
  const [updatedBy, setUpdatedBy] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const d = await api("/api/operator-filter");
      setCandidates(d.candidates);
      setVersion(d.version);
      setConfigured(d.configured);
      setUpdatedBy(d.updatedBy);
      // 从未保存时默认全选展示；保存过就严格还原库里那版勾选。
      setPicked(new Set(d.configured ? d.operators : d.candidates.map((c) => c.username)));
      setErr("");
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function toggle(name) {
    setPicked((cur) => {
      const next = new Set(cur);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  async function save() {
    setErr("");
    const operators = candidates.map((c) => c.username).filter((u) => picked.has(u));
    try {
      const d = await api("/api/operator-filter", {
        method: "PUT",
        body: JSON.stringify({ version, operators }),
      });
      setCandidates(d.candidates);
      setVersion(d.version);
      setConfigured(true);
      setUpdatedBy(d.updatedBy);
      setPicked(new Set(d.operators));
      onSaved();
    } catch (ex) {
      const cur = ex.data?.current;
      if (ex.status === 409 && cur) {
        // 另一位主管抢先提交：库里只留他那版，本地立即切到那版勾选。
        setCandidates(cur.candidates);
        setVersion(cur.version);
        setConfigured(cur.configured);
        setUpdatedBy(cur.updatedBy);
        setPicked(new Set(cur.operators));
        setErr(`${ex.message}（页面已切换为库里留下的版本，请核对后再保存）`);
      } else {
        setErr(ex.message);
      }
    }
  }

  const allOff = picked !== null && picked.size === 0;

  return (
    <div class="filterpage">
      <div class="card">
        <h2>采样人过滤</h2>
        <p class="viz-sub">
          勾选要看的操作人并保存。环盆底下的温谱与温谱台账同跟这一批勾选；没勾中的人两边都不露面。
        </p>
        {loading && <p>装载操作人…</p>}
        {!loading && !candidates.length && <p class="hint">还没有任何人登记过汤温。</p>}
        {!loading &&
          candidates.map((c) => (
            <label class="oprow" key={c.username}>
              <input
                type="checkbox"
                checked={picked.has(c.username)}
                onChange={() => toggle(c.username)}
              />
              <span class="opname">{c.username}</span>
              <span class="opcount">汤温 {c.readingCount} 次</span>
            </label>
          ))}
        {!loading && (
          <p class={`pickline ${allOff ? "warn" : ""}`}>
            已勾 {picked.size} / {candidates.length} 人
            {allOff && " · 当前一个都不勾，保存后温谱与台账都为空表"}
            {configured && updatedBy && !allOff ? ` · 库里版本 v${version}（${updatedBy} 保存）` : ""}
          </p>
        )}
        <div class="actions">
          <button class="primary" onClick={save} disabled={loading || picked === null}>
            保存勾选
          </button>
        </div>
        {err && <p class="err">{err}</p>}
      </div>
    </div>
  );
}

export function App() {
  const [ready, setReady] = useState(Boolean(token()));
  const [role, setRole] = useState("");
  const [view, setView] = useState("yard");

  useEffect(() => {
    if (!ready) return;
    api("/api/auth/me")
      .then((u) => setRole(u.role))
      .catch(() => {
        clearToken();
        setReady(false);
      });
  }, [ready]);

  if (!ready) {
    return <Login onOk={(r) => {
      setRole(r);
      setReady(true);
    }} />;
  }

  return (
    <div class="shell">
      <TopNav view={view} setView={setView} role={role} />
      {view === "yard" && <Yard active={view === "yard"} />}
      {view === "filter" && role === "admin" && (
        <FilterPage onSaved={() => setView("yard")} />
      )}
    </div>
  );
}

const root = document.getElementById("app");
if (root) {
  render(<App />, root);
}
