import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { api, clearToken, setToken, token } from "./api.js";
import "./app.css";

const STATUS_LABEL = { soaking: "浸茧", reeling: "缫丝中", reeled: "已缫完" };

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", { hour12: false });
}

function tempClass(t) {
  if (t < 38) return "cool";
  if (t > 42) return "hot";
  return "good";
}

function Login({ onOk }) {
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
      onOk(data.user);
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
        <p class="hint">已预填 admin / 123456，另有 worker / 123456</p>
        <button type="submit">登录</button>
      </form>
      {err && <p class="err">{err}</p>}
    </div>
  );
}

function TopBar({ view, onNav, onLogout }) {
  return (
    <div class="topbar">
      <strong class="brand">江口缫丝坞</strong>
      <nav class="nav">
        <button class={view === "yard" ? "tab active" : "tab"} onClick={() => onNav("yard")}>
          环盆作业台
        </button>
        <button class={view === "filter" ? "tab active" : "tab"} onClick={() => onNav("filter")}>
          采样人过滤
        </button>
      </nav>
      <button class="logout" onClick={onLogout}>
        退出
      </button>
    </div>
  );
}

function Spectrum({ readings }) {
  return (
    <section class="spectrum">
      <h2>温谱</h2>
      {readings.length === 0 ? (
        <p class="empty">暂无汤温记录</p>
      ) : (
        <div class="strip">
          {readings.map((r) => (
            <div
              key={r.id}
              class={`tick ${tempClass(r.waterTempC)}`}
              title={`${r.basinCode} · ${r.operator} · ${fmtTime(r.takenAt)}`}
            >
              <strong>{r.waterTempC}℃</strong>
              <span>{r.basinCode}</span>
              <span>{r.operator}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Ledger({ readings }) {
  return (
    <section class="ledger">
      <h2>温谱台账</h2>
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>盆位</th>
            <th>汤温℃</th>
            <th>操作人</th>
          </tr>
        </thead>
        <tbody>
          {readings.map((r) => (
            <tr key={r.id}>
              <td>{fmtTime(r.takenAt)}</td>
              <td>{r.basinCode}</td>
              <td>{r.waterTempC}</td>
              <td>{r.operator}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {readings.length === 0 && <p class="empty">暂无汤温记录</p>}
    </section>
  );
}

function Yard() {
  const [board, setBoard] = useState(null);
  const [picked, setPicked] = useState(null);
  const [temp, setTemp] = useState("40");
  const [err, setErr] = useState("");
  const [spectrum, setSpectrum] = useState([]);
  const [ledger, setLedger] = useState([]);

  async function refresh() {
    const [b, s, l] = await Promise.all([
      api("/api/board"),
      api("/api/readings/spectrum"),
      api("/api/readings/ledger"),
    ]);
    setBoard(b);
    setSpectrum(s.readings);
    setLedger(l.readings);
    if (picked) {
      setPicked(b.basins.find((x) => x.id === picked.id) || b.basins[0]);
    }
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, []);

  if (!board) {
    return (
      <div class="yard">
        {err || "装载环盆…"}
      </div>
    );
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
      <header class="yardhead">
        <h1>{board.filature}</h1>
        <p>{board.riverside} · 点盆登记汤温；已缫完须最近汤温 38～42℃</p>
      </header>
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
      <Spectrum readings={spectrum} />
      <Ledger readings={ledger} />
    </div>
  );
}

function FilterPage({ me }) {
  const isAdmin = me.role === "admin";
  const [operators, setOperators] = useState(null);
  const [checked, setChecked] = useState({});
  const [meta, setMeta] = useState(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [ops, filt] = await Promise.all([api("/api/operators"), api("/api/operator-filter")]);
        const selected = filt.saved ? new Set(filt.operators) : new Set(ops.operators);
        const map = {};
        ops.operators.forEach((op) => {
          map[op] = selected.has(op);
        });
        setOperators(ops.operators);
        setChecked(map);
        setMeta(filt.saved ? { by: filt.updatedBy, at: filt.updatedAt } : null);
      } catch (ex) {
        setErr(ex.message);
      }
    })();
  }, []);

  function toggle(op) {
    setChecked((prev) => ({ ...prev, [op]: !prev[op] }));
  }

  async function save() {
    setMsg("");
    setErr("");
    try {
      const picked = Object.keys(checked).filter((op) => checked[op]);
      const res = await api("/api/operator-filter", {
        method: "PUT",
        body: JSON.stringify({ operators: picked }),
      });
      setMeta({ by: res.updatedBy, at: res.updatedAt });
      setMsg("已保存：环盆作业台的温谱与温谱台账只显示被勾中的操作人。");
    } catch (ex) {
      setErr(ex.message);
    }
  }

  if (!operators) {
    return <div class="filterpage">{err || "装载操作人…"}</div>;
  }

  return (
    <div class="filterpage">
      <h1>采样人过滤</h1>
      <p class="hint">勾选要看的操作人；保存后温谱与温谱台账只出现被勾中的人，一个都不勾则两边都是空表。</p>
      {operators.length === 0 ? (
        <p class="empty">尚无操作人记录</p>
      ) : (
        <ul class="oplist">
          {operators.map((op) => (
            <li key={op}>
              <label>
                <input
                  type="checkbox"
                  checked={Boolean(checked[op])}
                  disabled={!isAdmin}
                  onChange={() => toggle(op)}
                />
                {op}
              </label>
            </li>
          ))}
        </ul>
      )}
      {isAdmin ? (
        <button onClick={save}>保存勾选</button>
      ) : (
        <p class="hint">仅管理员可改勾选，当前为只读。</p>
      )}
      {meta && (
        <p class="hint">
          当前版本由 {meta.by} 保存于 {fmtTime(meta.at)}
        </p>
      )}
      {msg && <p class="ok">{msg}</p>}
      {err && <p class="err">{err}</p>}
    </div>
  );
}

function App() {
  const [me, setMe] = useState(null);
  const [checking, setChecking] = useState(Boolean(token()));
  const [view, setView] = useState("yard");

  useEffect(() => {
    if (!token()) return;
    api("/api/auth/me")
      .then((u) => {
        setMe(u);
        setChecking(false);
      })
      .catch(() => {
        clearToken();
        setChecking(false);
      });
  }, []);

  if (checking) {
    return <div class="yard">装载…</div>;
  }
  if (!me) {
    return <Login onOk={(user) => setMe(user)} />;
  }
  return (
    <div>
      <TopBar
        view={view}
        onNav={setView}
        onLogout={() => {
          clearToken();
          location.reload();
        }}
      />
      {view === "yard" ? <Yard /> : <FilterPage me={me} />}
    </div>
  );
}

render(<App />, document.getElementById("app"));
