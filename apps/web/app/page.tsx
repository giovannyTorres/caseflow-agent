"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  api,
  ApiError,
  consultedPolicy,
  eventSummary,
  evidenceRetrieved,
  filterCases,
  isWorking,
  label,
  money,
  nextAction,
  sharedMovementFields,
  type CaseDetail,
  type CaseSummary,
  type Config,
  type User,
} from "@/lib/domain";

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </>
    ),
    arrow: (
      <>
        <path d="M5 12h14M13 6l6 6-6 6" />
      </>
    ),
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4 4" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    shield: (
      <>
        <path d="M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7Z" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    file: (
      <>
        <path d="M14 3H5v18h14V8Z" />
        <path d="M14 3v5h5M8 13h8M8 17h6" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 6v6l4 2" />
      </>
    ),
    bolt: <path d="m13 2-9 12h7l-1 8 10-13h-7Z" />,
    logout: (
      <>
        <path d="M9 5H4v14h5M10 12h11m-4-4 4 4-4 4" />
      </>
    ),
    chevron: <path d="m9 5 7 7-7 7" />,
    refresh: (
      <>
        <path d="M20 7v5h-5M4 17v-5h5" />
        <path d="M5 8a8 8 0 0 1 13-3l2 3M4 16l2 3a8 8 0 0 0 13-3" />
      </>
    ),
    user: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21v-2a8 8 0 0 1 16 0v2" />
      </>
    ),
  };
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name] || paths.file}
    </svg>
  );
}
const statusClass = (s: string) =>
  ["resolved", "approved", "completed"].includes(s)
    ? "positive"
    : ["failed", "rejected"].includes(s)
      ? "negative"
      : ["awaiting_approval", "proposed", "paused", "interrupted"].includes(s)
        ? "warning"
        : "neutral";
function Badge({ status }: { status: string }) {
  return (
    <span className={`badge ${statusClass(status)}`}>
      <i />
      {label(status)}
    </span>
  );
}
function DetailRecord({ record }: { record: Record<string, unknown> }) {
  return (
    <dl className="record">
      {Object.entries(record).map(([key, value]) => (
        <div key={key}>
          <dt>{label(key)}</dt>
          <dd>
            {typeof value === "object" ? JSON.stringify(value) : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null),
    [config, setConfig] = useState<Config | null>(null),
    [cases, setCases] = useState<CaseSummary[]>([]),
    [detail, setDetail] = useState<CaseDetail | null>(null);
  const [selected, setSelected] = useState(""),
    [query, setQuery] = useState(""),
    [status, setStatus] = useState("all"),
    [priorityFilter, setPriorityFilter] = useState("all"),
    [assigneeFilter, setAssigneeFilter] = useState("all"),
    [tab, setTab] = useState("overview"),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [persona, setPersona] = useState(""),
    [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState<
      "approve" | "reject" | "resolve" | null
    >(null),
    [editing, setEditing] = useState(false),
    [amount, setAmount] = useState(""),
    [reason, setReason] = useState("");
  const confirmationTrigger = useRef<HTMLElement | null>(null);
  function openConfirmation(action: "approve" | "reject" | "resolve") {
    confirmationTrigger.current = document.activeElement as HTMLElement | null;
    setConfirm(action);
  }
  const refresh = useCallback(async (id?: string) => {
    const all = await api<CaseSummary[]>("/cases");
    setCases(all);
    if (id) {
      const current = await api<CaseDetail>(`/cases/${id}`);
      setDetail({
        ...current,
        events: current.events || [],
        messages: current.messages || [],
        movements: current.movements || [],
        evidence: current.evidence || [],
      });
    }
  }, []);
  useEffect(() => {
    let alive = true;
    async function init() {
      try {
        const c = await api<Config>("/config");
        if (alive) {
          setConfig(c);
          setPersona(c.mode === "DEMO" ? "analyst" : "");
          setPassword(c.mode === "DEMO" ? "demo-pass" : "");
        }
        const current = await api<User>("/me");
        if (alive) {
          setUser(current);
          await refresh();
        }
      } catch (e) {
        if (alive && !(e instanceof ApiError && e.status === 401)) {
          setError("Workspace connection failed. Retry the connection before signing in.");
        }
      } finally {
        if (alive) setLoading(false);
      }
    }
    void init();
    return () => {
      alive = false;
    };
  }, [refresh]);
  useEffect(() => {
    if (!selected) return;
    let alive = true;
    api<CaseDetail>(`/cases/${selected}`)
      .then((current) => {
        if (alive)
          setDetail({
            ...current,
            events: current.events || [],
            messages: current.messages || [],
            movements: current.movements || [],
            evidence: current.evidence || [],
          });
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [selected]);
  useEffect(() => {
    if (!user) return;
    const timer = setInterval(
      () => {
        void refresh(selected)
          .then(() => setError((previous) => previous.startsWith("Refresh failed.") ? "" : previous))
          .catch((e) => {
            if (e instanceof ApiError && e.status === 401) {
              setUser(null);
              setDetail(null);
              setSelected("");
              setError("Your session expired. Sign in again.");
            } else {
              setError("Refresh failed. Retrying the connection automatically.");
            }
          });
      },
      ["queued", "running", "pending", "processing"].includes(
        detail?.job?.status || "",
      )
        ? 1000
        : 5000,
    );
    return () => clearInterval(timer);
  }, [user, selected, detail?.job?.status, refresh]);
  useEffect(() => {
    if (!confirm) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) setConfirm(null);
      if (e.key === "Tab") {
        const focusable = Array.from(
          document.querySelectorAll<HTMLElement>(
            "[role=dialog] button:not(:disabled),[role=dialog] input",
          ),
        );
        const first = focusable[0],
          last = focusable.at(-1);
        if (!focusable.length) {
          e.preventDefault();
          return;
        }
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (!document.querySelector("[role=dialog]")) confirmationTrigger.current?.focus();
    };
  }, [confirm, busy]);
  async function login(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/login", { username: persona, password });
      setUser(await api<User>("/me"));
      await refresh();
      setNotice(`Signed in as ${persona}.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    try {
      await api("/auth/logout", {});
      setUser(null);
      setSelected("");
      setDetail(null);
      setNotice("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function action(name: string, body: unknown = {}) {
    if (!selected) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(`/cases/${selected}/${name}`, body);
      await refresh(selected);
      setNotice(
        name === "investigate"
          ? "Investigation queued. Progress is saved as tools complete."
          : name === "resolve"
            ? "Resolution recorded in the synthetic simulator."
            : name === "proposal"
              ? "Proposal updated. Previous approvals are invalidated."
              : `${label(name)} recorded.`,
      );
      setConfirm(null);
      setEditing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const visible = filterCases(cases, query, status).filter(
      (c) =>
        (priorityFilter === "all" || c.priority === priorityFilter) &&
        (assigneeFilter === "all" || c.assignee === assigneeFilter),
    ),
    active = cases.filter(
      (c) => !["resolved", "rejected"].includes(c.status),
    ).length,
    pending = cases.filter((c) =>
      ["awaiting_approval", "proposed"].includes(c.status),
    ).length,
    resolved = cases.filter((c) => c.status === "resolved").length;
  const mode = config?.mode || user?.mode || "UNAVAILABLE";
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to workspace
      </a>
      <aside className="sidebar">
        <Link href="/" className="brand" aria-label="Caseflow home">
          <span className="brand-mark">
            <span />
            <span />
            <span />
          </span>
          <span>
            caseflow<span className="brand-dot">.</span>
          </span>
        </Link>
        <div className="workspace-label">
          <span className="org-logo">A</span>
          <span>
            Aster Finance<small>Synthetic organization</small>
          </span>
        </div>
        {user && (
          <>
            <p className="nav-label">Workspace</p>
            <nav aria-label="Main navigation">
              <button
                className="nav-item active"
                onClick={() => {
                  setSelected("");
                  setDetail(null);
                  setStatus("all");
                  setQuery("");
                  setPriorityFilter("all");
                  setAssigneeFilter("all");
                }}
              >
                <Icon name="grid" />
                Case inbox<span className="nav-count">{cases.length || "—"}</span>
              </button>
              <button
                className="nav-item"
                onClick={() => {
                  setStatus("awaiting_approval");
                  setSelected("");
                  setDetail(null);
                }}
              >
                <Icon name="shield" />
                Review queue
                {pending > 0 && <span className="nav-count">{pending}</span>}
              </button>
              <a
                className="nav-item"
                href="/api/docs"
                target="_blank"
                rel="noreferrer"
              >
                <Icon name="file" />
                API reference
                <Icon name="arrow" size={14} />
              </a>
            </nav>
          </>
        )}
        {user && (
        <div className="sidebar-bottom">
          <div className="user-card">
            <span className="avatar">
              {user?.role === "supervisor" ? "S" : "A"}
            </span>
            <div>
              <strong>{user ? label(user.username) : "Sign in"}</strong>
              <small>
                {user ? label(user.role) : "An account is required"}
              </small>
            </div>
            {user && (
              <button
                className="icon-button"
                onClick={logout}
                aria-label="Sign out"
              >
                <Icon name="logout" size={18} />
              </button>
            )}
          </div>
        </div>
        )}
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span>{" "}
            <strong>
              {!user ? "Sign in" : selected ? "Case investigation" : "Case inbox"}
            </strong>
          </div>
          <div className="topbar-right">
            <span
              className={`mode-badge ${mode.toUpperCase() === "LIVE" ? "live" : ""}`}
            >
              <i />
              {mode.toUpperCase()} MODE
            </span>
            <span className="environment-label">Synthetic data only</span>
          </div>
        </header>
        <main id="main">
          {error && (
            <div role="alert" className="alert error">
              <strong>Action needs attention</strong>
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss error">
                ×
              </button>
            </div>
          )}
          {notice && (
            <div role="status" className="alert success">
              <Icon name="check" size={18} />
              <span>{notice}</span>
              <button
                onClick={() => setNotice("")}
                aria-label="Dismiss notification"
              >
                ×
              </button>
            </div>
          )}
          {loading ? (
            <div className="loading-state" role="status">
              <span className="spinner" />
              Opening your workspace…
            </div>
          ) : !user ? (
            <section className="login-layout">
              <div className="login-intro">
                <h1>
                  From a disputed charge
                  <br />
                  to a clear decision<span>.</span>
                </h1>
                <p>
                  Investigate synthetic cases with connected tools, traceable
                  evidence, and an approval at every consequential step.
                </p>
                <div className="login-proof">
                  <span>
                    <Icon name="file" />
                    Real tool execution
                  </span>
                  <span>
                    <Icon name="shield" />
                    Server-enforced controls
                  </span>
                  <span>
                    <Icon name="clock" />
                    Persistent case history
                  </span>
                </div>
                <div className="process-preview">
                  <span>Analyst investigates</span>
                  <Icon name="arrow" />
                  <span>Supervisor approves</span>
                  <Icon name="arrow" />
                  <span>Simulator records once</span>
                </div>
              </div>
              <form className="login-card" onSubmit={login}>
                <h2>Sign in</h2>
                <p>{mode === "DEMO" ? "Choose a demo role to explore a complete investigation." : "Sign in with the account provisioned by your operator."}</p>
                {mode === "DEMO" ? <>
                <label htmlFor="persona">Workspace role</label>
                <select
                  id="persona"
                  value={persona}
                  onChange={(e) => setPersona(e.target.value)}
                >
                  <option value="analyst">
                    Analyst · Investigate & propose
                  </option>
                  <option value="supervisor">
                    Supervisor · Review & authorize
                  </option>
                </select>
                </> : <>
                  <label htmlFor="persona">Username</label>
                  <input id="persona" autoComplete="username" value={persona}
                    onChange={(e) => setPersona(e.target.value)} maxLength={80} required />
                </>}
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  maxLength={128}
                />
                {mode === "DEMO" && (
                <small className="credential-note">
                  Demo credentials: analyst or supervisor / demo-pass
                </small>
                )}
                <button className="button primary wide" disabled={busy || !config}>
                  {busy ? "Opening workspace…" : "Enter workspace"}
                  <Icon name="arrow" size={18} />
                </button>
                {!config && <button type="button" className="button secondary wide" onClick={() => window.location.reload()}>Retry connection</button>}
                <div className="demo-note">
                  <span className="badge neutral">{mode.toUpperCase()}</span>
                  <p>
                    {mode === "DEMO" ? <>Example decisions are deterministic. Tools, permissions and
                    persistence execute for real. Free-form AI decisions require
                    LIVE configuration.</> : mode === "LIVE" ? <>Model decisions use the configured provider. Missing configuration or provider errors never switch to demo responses.</> : <>The server mode is unavailable until the connection is restored.</>}
                  </p>
                </div>
              </form>
            </section>
          ) : (
            <>
              {!selected ? (
                <>
                  <section className="page-heading">
                    <div>
                      <h1>Case inbox</h1>
                      <p>
                        Disputed charges waiting for investigation or
                        supervisor review. Every amount and identity is
                        synthetic.
                      </p>
                    </div>
                    <button
                      className="button secondary"
                      onClick={() => {
                        setBusy(true);
                        refresh()
                          .catch((e) => setError(e.message))
                          .finally(() => setBusy(false));
                      }}
                      disabled={busy}
                    >
                      <Icon name="refresh" size={16} />
                      Refresh queue
                    </button>
                  </section>
                  <section className="stats" aria-label="Queue summary">
                    <div className="stat">
                      <div>
                        <span>Active cases</span>
                        <strong>{active}</strong>
                        <small>Ready for your next action</small>
                      </div>
                    </div>
                    <div className="stat">
                      <div>
                        <span>Awaiting review</span>
                        <strong>{pending}</strong>
                        <small>Human authorization needed</small>
                      </div>
                    </div>
                    <div className="stat">
                      <div>
                        <span>Resolved</span>
                        <strong>{resolved}</strong>
                        <small>Recorded in the simulator</small>
                      </div>
                    </div>
                  </section>
                  <section className="queue-panel">
                    <div className="panel-heading">
                      <div>
                        <h2>
                          Cases{" "}
                          <span className="soft-count">{cases.length}</span>
                        </h2>
                      </div>
                    </div>
                    <div className="filters">
                      <label className="search">
                        <Icon name="search" size={18} />
                        <input
                          aria-label="Search cases"
                          value={query}
                          onChange={(e) => setQuery(e.target.value)}
                          placeholder="Search cases, scenarios or assignees…"
                        />
                      </label>
                      <label className="filter-label">
                        <span>Status</span>
                        <select
                          aria-label="Filter by status"
                          value={status}
                          onChange={(e) => setStatus(e.target.value)}
                        >
                          <option value="all">All statuses</option>
                          {[
                            ...new Set([
                              ...cases.map((c) => c.status),
                              "awaiting_approval",
                            ]),
                          ].map((s) => (
                            <option key={s} value={s}>
                              {label(s)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="filter-label">
                        <span>Priority</span>
                        <select
                          aria-label="Filter by priority"
                          value={priorityFilter}
                          onChange={(e) => setPriorityFilter(e.target.value)}
                        >
                          <option value="all">All priorities</option>
                          {[...new Set(cases.map((c) => c.priority))].map(
                            (p) => (
                              <option key={p} value={p}>
                                {label(p)}
                              </option>
                            ),
                          )}
                        </select>
                      </label>
                      <label className="filter-label">
                        <span>Owner</span>
                        <select
                          aria-label="Filter by assignee"
                          value={assigneeFilter}
                          onChange={(e) => setAssigneeFilter(e.target.value)}
                        >
                          <option value="all">All assignees</option>
                          {[...new Set(cases.map((c) => c.assignee))].map(
                            (a) => (
                              <option key={a} value={a}>
                                {label(a)}
                              </option>
                            ),
                          )}
                        </select>
                      </label>
                    </div>
                    <div className="case-table">
                      <div className="table-head">
                        <span>Case</span>
                        <span>Priority</span>
                        <span>Amount</span>
                        <span>Status</span>
                        <span />
                      </div>
                      {visible.map((c) => (
                        <button
                          key={c.id}
                          className="case-row"
                          onClick={() => {
                            setSelected(c.id);
                            setDetail(null);
                            setTab("overview");
                            setNotice("");
                          }}
                        >
                          <div className="case-name">
                            <div>
                              <strong>{c.title}</strong>
                              <small>
                                {c.id.slice(0, 12)} <span>·</span>{" "}
                                {label(c.scenario)}
                              </small>
                            </div>
                          </div>
                          <span className={`priority ${c.priority}`}>
                            <i />
                            {label(c.priority)}
                          </span>
                          <span className="amount">
                            {money(c.amount, c.currency)}
                          </span>
                          <Badge status={c.status} />
                          <Icon name="chevron" size={16} />
                        </button>
                      ))}
                    </div>
                    {!visible.length && (
                      <div className="empty-state">
                        <Icon name="search" size={28} />
                        <h3>No cases match this view</h3>
                        <p>Try another search or clear the status filter.</p>
                        <button
                          className="button secondary"
                          onClick={() => {
                            setQuery("");
                            setStatus("all");
                            setPriorityFilter("all");
                            setAssigneeFilter("all");
                          }}
                        >
                          Clear filters
                        </button>
                      </div>
                    )}
                    <div className="queue-footer">
                      <span>
                        Showing {visible.length} of {cases.length} cases
                      </span>
                      <span>
                        <Icon name="shield" size={14} />
                        All amounts and identities are synthetic
                      </span>
                    </div>
                  </section>
                </>
              ) : (
                <>
                  <button
                    className="back-button"
                    onClick={() => {
                      setSelected("");
                      setDetail(null);
                    }}
                  >
                    ← Back to case inbox
                  </button>
                  {!detail ? (
                    <div className="loading-state" role="status">
                      <span className="spinner" />
                      Loading case evidence…
                    </div>
                  ) : (
                    <>
                      <section className="page-heading detail-heading">
                        <div>
                          <span className="eyebrow">
                            {detail.id} / {label(detail.scenario)}
                          </span>
                          <h1>{detail.title}</h1>
                          <p>
                            <span className={`priority ${detail.priority}`}>
                              <i />
                              {label(detail.priority)} priority
                            </span>
                            <span className="separator">·</span>Assigned to{" "}
                            {label(detail.assignee)}
                          </p>
                        </div>
                        <Badge status={detail.status} />
                      </section>
                      <div className="workflow">
                        <div className="workflow-step done">
                          <span>1</span>
                          <div>
                            <strong>Case opened</strong>
                            <small>Synthetic charge received</small>
                          </div>
                        </div>
                        <div
                          className={`workflow-step ${detail.proposal || evidenceRetrieved(detail.events) ? "done" : isWorking(detail.job) ? "current" : ""}`}
                        >
                          <span>2</span>
                          <div>
                            <strong>Investigate</strong>
                            <small>MCP evidence & policy tools</small>
                          </div>
                        </div>
                        <div
                          className={`workflow-step ${["approved", "resolved", "rejected"].includes(detail.status) ? "done" : detail.proposal || detail.status === "needs_evidence" ? "current" : ""}`}
                        >
                          <span>3</span>
                          <div>
                            <strong>Human review</strong>
                            <small>Approval tied to proposal version</small>
                          </div>
                        </div>
                        <div
                          className={`workflow-step ${detail.status === "resolved" ? "done" : ""}`}
                        >
                          <span>4</span>
                          <div>
                            <strong>Resolve</strong>
                            <small>Record simulator outcome</small>
                          </div>
                        </div>
                      </div>
                      <div className="detail-grid">
                        <section className="detail-main">
                          <div
                            className="tabs"
                            role="tablist"
                            aria-label="Case detail"
                          >
                            {["overview", "evidence", "activity"].map((t) => (
                              <button
                                key={t}
                                role="tab"
                                aria-selected={tab === t}
                                onClick={() => setTab(t)}
                                className={tab === t ? "selected" : ""}
                              >
                                {label(t)}
                                {t === "evidence" && (
                                  <span>{detail.evidence.length}</span>
                                )}
                                {t === "activity" && (
                                  <span>{detail.events.length}</span>
                                )}
                              </button>
                            ))}
                          </div>
                          <div className="tab-content" role="tabpanel">
                            {tab === "overview" ? (
                              <>
                                <div className="section-header">
                                  <h2>Investigation workspace</h2>
                                  <span className="badge neutral">
                                    {mode.toUpperCase()} decisions
                                  </span>
                                </div>
                                <p className="muted">
                                  The agent consults connected tools and
                                  prepares a proposal. A supervisor authorizes
                                  each outcome.
                                </p>
                                {detail.job && (
                                  <div
                                    className={`job-panel ${detail.job.status === "failed" ? "job-failed" : ""}`}
                                  >
                                    <span>
                                      {isWorking(detail.job) ? (
                                        <span className="spinner" />
                                      ) : (
                                        <Icon name="clock" />
                                      )}
                                    </span>
                                    <div>
                                      <strong>
                                        Investigation{" "}
                                        {label(detail.job.status).toLowerCase()}
                                      </strong>
                                      <p>
                                        {detail.job.error ||
                                          "Progress and checkpoints are saved to the case record."}
                                      </p>
                                    </div>
                                  </div>
                                )}
                                {detail.messages.length ? (
                                  <div className="conversation">
                                    {detail.messages.map((m, i) => (
                                      <article className="message" key={i}>
                                        <span className="message-icon">
                                          <Icon
                                            name={
                                              m.role === "user"
                                                ? "user"
                                                : "bolt"
                                            }
                                            size={16}
                                          />
                                        </span>
                                        <div>
                                          <strong>
                                            {m.role === "assistant"
                                              ? "Caseflow agent"
                                              : label(m.role)}
                                          </strong>
                                          <p>{m.content}</p>
                                        </div>
                                      </article>
                                    ))}
                                  </div>
                                ) : (
                                  <div className="investigation-empty">
                                    <span className="large-icon">
                                      <Icon name="bolt" size={28} />
                                    </span>
                                    <h3>No findings yet</h3>
                                    <p>
                                      The investigation retrieves the movements
                                      and the policy, then proposes a
                                      resolution or requests more evidence.
                                    </p>
                                  </div>
                                )}
                                {detail.movements.length > 0 && (() => {
                                  const shared = sharedMovementFields(detail.movements);
                                  const columns = ["id", "merchant", "amount", "currency", "posted_at"].filter(
                                    (k) => detail.movements.some((m) => m[k] !== undefined),
                                  );
                                  return (
                                    <section className="evidence-block">
                                      <div className="evidence-heading">
                                        <h3 className="subheading">
                                          {evidenceRetrieved(detail.events)
                                            ? "Retrieved movements"
                                            : "Disputed movements on file"}
                                        </h3>
                                        <span className="source-tag">
                                          {evidenceRetrieved(detail.events)
                                            ? "MCP · get_movements"
                                            : "Not yet retrieved by the agent"}
                                        </span>
                                      </div>
                                      <div className="table-scroll">
                                        <table className="movement-table">
                                          <thead>
                                            <tr>
                                              {columns.map((k) => (
                                                <th key={k} scope="col">
                                                  {label(k)}
                                                </th>
                                              ))}
                                            </tr>
                                          </thead>
                                          <tbody>
                                            {detail.movements.map((m, i) => (
                                              <tr key={i}>
                                                {columns.map((k) => (
                                                  <td
                                                    key={k}
                                                    className={shared.includes(k as never) ? "same" : ""}
                                                  >
                                                    {k === "amount" && typeof m[k] === "number"
                                                      ? money(m[k] as number, String(m.currency ?? detail.currency))
                                                      : String(m[k] ?? "—")}
                                                  </td>
                                                ))}
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      </div>
                                      {shared.length > 0 && (
                                        <p className="match-note">
                                          <i aria-hidden="true" />
                                          Same {shared.map((f) => (f === "posted_at" ? "posting time" : f)).join(", ")} on every movement
                                        </p>
                                      )}
                                    </section>
                                  );
                                })()}
                                {(() => {
                                  const policy = consultedPolicy(detail.events);
                                  return policy ? (
                                    <section className="evidence-block">
                                      <div className="evidence-heading">
                                        <h3 className="subheading">Consulted policy</h3>
                                        <span className="source-tag">
                                          MCP · get_policy · {policy.id}
                                          {policy.version ? ` v${policy.version}` : ""}
                                        </span>
                                      </div>
                                      {policy.text && (
                                        <blockquote className="policy-text">{policy.text}</blockquote>
                                      )}
                                    </section>
                                  ) : null;
                                })()}
                              </>
                            ) : tab === "evidence" ? (
                              <>
                                <div className="section-header">
                                  <h2>Evidence collection</h2>
                                  <span className="soft-count">
                                    {detail.evidence.length}
                                  </span>
                                </div>
                                <p className="muted">
                                  Evidence requests and attached records for
                                  this case. Retrieved movements and the
                                  consulted policy appear in Overview.
                                </p>
                                {detail.evidence.length ? (
                                  <div className="record-grid">
                                    {detail.evidence.map((e, i) => (
                                      <DetailRecord key={i} record={e} />
                                    ))}
                                  </div>
                                ) : (
                                  <div className="empty-state">
                                    <Icon name="file" size={28} />
                                    <h3>No evidence requests</h3>
                                    <p>
                                      The investigation asks for extra evidence
                                      here only when the retrieved records are
                                      not enough.
                                    </p>
                                  </div>
                                )}
                              </>
                            ) : (
                              <>
                                <div className="section-header">
                                  <h2>Case activity</h2>
                                  <span className="badge neutral">
                                    Audit trail
                                  </span>
                                </div>
                                <p className="muted">
                                  Operational events only. Private model
                                  reasoning is never displayed.
                                </p>
                                <ol className="timeline">
                                  {detail.events.map((e, i) => (
                                    <li key={e.id || i}>
                                      <span className="timeline-dot" />
                                      <div>
                                        <strong>{label(e.event)}</strong>
                                        <p>{eventSummary(e, detail.currency)}</p>
                                        <small>
                                          {label(e.actor)} ·{" "}
                                          {new Date(
                                            e.created_at,
                                          ).toLocaleString()}
                                        </small>
                                      </div>
                                    </li>
                                  ))}
                                </ol>
                                {!detail.events.length && (
                                  <p className="empty-state">
                                    No activity has been recorded.
                                  </p>
                                )}
                              </>
                            )}
                          </div>
                        </section>
                        <aside className="case-aside">
                          <section className="summary-card">
                            <div className="section-kicker">
                              Disputed amount
                            </div>
                            <div className="disputed-amount">
                              {money(detail.amount, detail.currency)}
                            </div>
                            <span className="muted">
                              {detail.currency} · Synthetic charge
                            </span>
                            <hr />
                            <div className="section-header">
                              <h3>Next action</h3>
                              <Icon name="bolt" size={16} />
                            </div>
                            <p className="muted">
                              {nextAction(
                                detail.status,
                                user.role,
                                detail.proposal?.version,
                              )}
                            </p>
                            {["new", "investigating", "running"].includes(detail.status) ? (
                              <button
                                className="button primary wide"
                                disabled={busy || isWorking(detail.job)}
                                onClick={() => action("investigate")}
                              >
                                <Icon name="bolt" size={16} />
                                {isWorking(detail.job) ? "Investigation in progress" : "Run investigation"}
                              </button>
                            ) : (
                              <div className="review-note">
                                <Icon name="shield" size={16} />
                                {({
                                  awaiting_approval: "Investigation complete. Awaiting supervisor review of this proposal.",
                                  approved: "Approved version ready for a supervisor to record the resolution.",
                                  resolved: "Resolution recorded. This case is complete.",
                                  rejected: "Case rejected. This case is closed.",
                                  needs_evidence: "Evidence requested; supervisor review pending.",
                                  failed: "A tool could not complete the investigation. Resume to retry from saved progress.",
                                  interrupted: "Investigation interrupted. Resume from the saved checkpoint.",
                                } as Record<string, string>)[detail.status] || "Review the case activity for the next authorized action."}
                              </div>
                            )}
                            {(["failed", "paused", "interrupted"].includes(
                              detail.job?.status || "",
                            ) ||
                              detail.status === "interrupted") && (
                              <button
                                className="button secondary wide"
                                onClick={() => action("resume")}
                                disabled={busy}
                              >
                                <Icon name="refresh" size={16} />
                                Resume investigation
                              </button>
                            )}
                          </section>
                          <section className="proposal-card">
                            <div className="section-header">
                              <h3>Resolution proposal</h3>
                              {detail.proposal && (
                                <span className="version">
                                  v{detail.proposal.version}
                                </span>
                              )}
                            </div>
                            {detail.proposal ? (
                              <>
                                <Badge status={detail.proposal.status} />
                                <div className="proposal-amount">
                                  {money(
                                    detail.proposal.amount,
                                    detail.currency,
                                  )}
                                </div>
                                <p>{detail.proposal.reason}</p>
                                {!["resolved", "rejected"].includes(detail.status) && (
                                  <>
                                    <button
                                      className="text-button"
                                      onClick={() => {
                                        setEditing(!editing);
                                        setAmount(
                                          String(detail.proposal!.amount),
                                        );
                                        setReason(detail.proposal!.reason);
                                      }}
                                    >
                                      Edit proposal
                                    </button>
                                    {editing && (
                                      <form
                                        className="edit-form"
                                        onSubmit={(e) => {
                                          e.preventDefault();
                                          void action("proposal", {
                                            amount: Number(amount),
                                            reason,
                                          });
                                        }}
                                      >
                                        <label htmlFor="amount">
                                          Proposed amount
                                        </label>
                                        <input
                                          id="amount"
                                          type="number"
                                          min="1"
                                          max={detail.amount}
                                          step="1"
                                          required
                                          value={amount}
                                          onChange={(e) =>
                                            setAmount(e.target.value)
                                          }
                                        />
                                        <label htmlFor="reason">
                                          Evidence-based reason
                                        </label>
                                        <textarea
                                          id="reason"
                                          value={reason}
                                          onChange={(e) =>
                                            setReason(e.target.value)
                                          }
                                          required
                                        />
                                        <p className="muted">
                                          Saving a new version invalidates
                                          earlier approvals.
                                        </p>
                                        <button
                                          className="button secondary wide"
                                          disabled={busy}
                                        >
                                          Save new version
                                        </button>
                                      </form>
                                    )}
                                    {user.role === "supervisor" ? (
                                      <div className="approval-actions">
                                        {detail.status === "approved" ? (
                                          <button
                                            className="button primary wide"
                                            disabled={busy}
                                            onClick={() => openConfirmation("resolve")}
                                          >
                                            <Icon name="check" size={16} />
                                            Record resolution
                                          </button>
                                        ) : (
                                          <button
                                            className="button primary wide"
                                            disabled={busy}
                                            onClick={() => openConfirmation("approve")}
                                          >
                                            <Icon name="shield" size={16} />
                                            Approve v{detail.proposal.version}
                                          </button>
                                        )}
                                        <button
                                          className="button ghost-danger wide"
                                          disabled={busy}
                                          onClick={() => openConfirmation("reject")}
                                        >
                                          Reject proposal
                                        </button>
                                      </div>
                                    ) : (
                                      <div className="review-note">
                                        <Icon name="shield" size={16} />A
                                        supervisor must approve this exact
                                        version before resolution.
                                      </div>
                                    )}
                                  </>
                                )}
                              </>
                            ) : (
                              <>
                                <div className="proposal-empty">
                                  <Icon name="file" size={24} />
                                  <p>{detail.status === "rejected" ? "The supervisor rejected this case. The decision remains in the audit trail." : "A proposal appears here once the investigation has enough evidence."}</p>
                                </div>
                                {detail.status === "needs_evidence" && user.role === "supervisor" && (
                                  <button className="button danger wide" disabled={busy} onClick={() => openConfirmation("reject")}>
                                    Reject case
                                  </button>
                                )}
                              </>
                            )}
                          </section>
                          <div className="case-security">
                            <Icon name="shield" size={16} />
                            <p>
                              Authorization runs on the server. Repeated
                              resolution requests cannot create duplicate
                              actions.
                            </p>
                          </div>
                        </aside>
                      </div>
                    </>
                  )}
                </>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>Caseflow · portfolio project</span>
            <span>Fictional organization. No real financial actions.</span>
          </footer>
          {config && mode.toUpperCase() === "LIVE" && !config.live_ready && (
            <div role="alert" className="alert error">
              <strong>LIVE configuration incomplete</strong>
              <span>{config.missing.join(", ")}</span>
            </div>
          )}
        </main>
      </div>
      {confirm && detail && (
        <div
          className="modal-backdrop"
          onClick={() => !busy && setConfirm(null)}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            className="modal"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="large-icon">
              <Icon name="shield" size={26} />
            </span>
            <h2 id="confirm-title">
              {detail.proposal ? `${label(confirm)} proposal v${detail.proposal.version}?` : "Reject this case?"}
            </h2>
            <p>
              {confirm === "resolve"
                ? "This records an outcome in the synthetic simulator. A valid approval for this exact version is required."
                : confirm === "approve"
                  ? "Your approval applies only to this proposal version. Any later edit requires a new review."
                  : detail.proposal ? "This rejects the current proposal and records your decision in the audit trail." : "This closes the case without a reimbursement and records your decision in the audit trail."}
            </p>
            <div className="confirm-summary">
              <span>{detail.title}</span>
              <strong>{money(detail.proposal?.amount ?? detail.amount, detail.currency)}</strong>
            </div>
            {error && (
              <p role="alert" className="alert error">
                {error}
              </p>
            )}
            <div className="modal-actions">
              <button
                className="button secondary"
                autoFocus
                onClick={() => setConfirm(null)}
                disabled={busy}
              >
                Cancel
              </button>
              <button
                className="button primary"
                disabled={busy}
                onClick={() =>
                  action(confirm, { version: detail.proposal?.version ?? 0 })
                }
              >
                {busy ? "Recording…" : `Confirm ${confirm}`}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
