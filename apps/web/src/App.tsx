import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ReactNode, useEffect, useState, useSyncExternalStore } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api, getToken, onAuthChange, setToken } from "./api/client";
import type { Project, User } from "./api/types";
import { BrandMark, Icon } from "./components/Icon";
import { Loading } from "./components/ui";
import { journalCount } from "./lib/offline";
import { AdminPage } from "./pages/Admin";
import { AgentsPage } from "./pages/Agents";
import { BiblePage } from "./pages/Bible";
import { ContinuityPage } from "./pages/Continuity";
import { DashboardPage } from "./pages/Dashboard";
import { GraphPage, TimelinePage } from "./pages/Views";
import { InsightPage } from "./pages/Insight";
import { LoginPage } from "./pages/Login";
import { ProjectsPage } from "./pages/Projects";
import { ProposalsPage } from "./pages/Proposals";
import { PublishPage } from "./pages/Publish";
import { SettingsPage } from "./pages/Settings";
import { SourcesPage } from "./pages/Sources";
import { WritePage } from "./pages/Write";

function useToken() {
  return useSyncExternalStore((cb) => { const off = onAuthChange(cb); return () => { off(); }; }, getToken);
}

export function useMe() {
  return useQuery<User>({ queryKey: ["me"], queryFn: () => api("/v1/auth/me"), enabled: !!getToken() });
}

export function App() {
  const token = useToken();
  if (!token) {
    return (
      <Routes>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="/" element={<Shell><ProjectsPage /></Shell>} />
      <Route path="/admin" element={<Shell><AdminPage /></Shell>} />
      <Route path="/p/:pid/*" element={<ProjectRoutes />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function ProjectRoutes() {
  return (
    <Routes>
      <Route index element={<Shell project><DashboardPage /></Shell>} />
      <Route path="write/:nodeId?" element={<Shell project flush><WritePage /></Shell>} />
      <Route path="bible" element={<Shell project><BiblePage /></Shell>} />
      <Route path="timeline" element={<Shell project><TimelinePage /></Shell>} />
      <Route path="graph" element={<Shell project><GraphPage /></Shell>} />
      <Route path="continuity" element={<Shell project><ContinuityPage /></Shell>} />
      <Route path="sources" element={<Shell project><SourcesPage /></Shell>} />
      <Route path="agents" element={<Shell project><AgentsPage /></Shell>} />
      <Route path="proposals" element={<Shell project><ProposalsPage /></Shell>} />
      <Route path="publish" element={<Shell project><PublishPage /></Shell>} />
      <Route path="insight" element={<Shell project><InsightPage /></Shell>} />
      <Route path="settings" element={<Shell project><SettingsPage /></Shell>} />
    </Routes>
  );
}

export function useProject() {
  const { pid } = useParams();
  return useQuery<Project>({ queryKey: ["project", pid], queryFn: () => api(`/v1/projects/${pid}`), enabled: !!pid });
}

function useOnline() {
  const [on, setOn] = useState(navigator.onLine);
  useEffect(() => {
    const a = () => setOn(true), b = () => setOn(false);
    window.addEventListener("online", a);
    window.addEventListener("offline", b);
    return () => { window.removeEventListener("online", a); window.removeEventListener("offline", b); };
  }, []);
  return on;
}

function Shell({ children, project, flush }: { children: ReactNode; project?: boolean; flush?: boolean }) {
  const { pid } = useParams();
  const me = useMe();
  const qc = useQueryClient();
  const nav = useNavigate();
  const online = useOnline();
  const proj = useProject();
  const catalog = useQuery<any>({ queryKey: ["catalog"], queryFn: () => api("/v1/agents/catalog"), staleTime: 60_000 });
  const dash = useQuery<any>({ queryKey: ["dashboard", pid], queryFn: () => api(`/v1/projects/${pid}/dashboard`), enabled: !!project && !!pid });
  const pending = useQuery({ queryKey: ["journal-count"], queryFn: journalCount, refetchInterval: 4000 });
  const [theme, setTheme] = useState(document.documentElement.dataset.theme || "dark");
  const toggleTheme = () => {
    const t = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("nis.theme", t); } catch { /* ignore */ }
    setTheme(t);
  };
  const logout = async () => {
    try { await api("/v1/auth/logout", { method: "POST" }); } catch { /* ignore */ }
    setToken(null);
    qc.clear();
    nav("/");
  };
  const provider = catalog.data?.provider;
  const d = dash.data;
  const link = (to: string, icon: string, label: string, badge?: ReactNode) => (
    <NavLink to={to} end className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
      <Icon name={icon} size={17} /> <span>{label}</span> {badge}
    </NavLink>
  );
  const highConf = d?.open_conflicts?.high || 0;
  const openConf = d ? d.open_conflicts.high + d.open_conflicts.medium + d.open_conflicts.low : 0;
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <BrandMark />
          <div>استوديو ذكاء الرواية<small>NIS · CONTROL</small></div>
        </div>
        {project && proj.data && (
          <div className="row" style={{ gap: 6 }}>
            <span className="dim">/</span>
            <strong>{proj.data.title}</strong>
            <span className="badge">{roleLabel(proj.data.role)}</span>
          </div>
        )}
        <div className="spacer" />
        <span className="row dim" title="حالة الاتصال">
          <span className={`dot ${online ? "ok" : "bad pulse"}`} /> {online ? "متصل" : "غير متصل — الحفظ محلي"}
        </span>
        {!!pending.data && <span className="badge warn" title="تعديلات محفوظة محلياً لم تُزامن بعد">{pending.data} بانتظار المزامنة</span>}
        <span className="row dim" title={provider?.message || ""}>
          <Icon name="agents" size={15} />
          {provider ? (provider.available ? `${provider.name} · ${provider.external ? "خارجي" : "محلي"}` : "الوكلاء: تحليل حتمي") : "…"}
        </span>
        <button className="btn ghost icon" onClick={toggleTheme} aria-label="تبديل السمة"><Icon name={theme === "dark" ? "sun" : "moon"} /></button>
        <span className="dim">{me.data?.display_name}</span>
        <button className="btn ghost icon" onClick={logout} aria-label="خروج" title="خروج"><Icon name="logout" /></button>
      </header>
      <nav className="sidebar" aria-label="التنقل">
        <div className="nav-section">عام</div>
        {link("/", "projects", "المشاريع")}
        {me.data?.is_admin && link("/admin", "admin", "لوحة المسؤول")}
        {project && pid && (
          <>
            <div className="nav-section">المشروع</div>
            {link(`/p/${pid}`, "dashboard", "مركز القيادة")}
            {link(`/p/${pid}/write`, "write", "غرفة الكتابة")}
            <div className="nav-section">عالم الرواية</div>
            {link(`/p/${pid}/bible`, "bible", "الكتاب المرجعي")}
            {link(`/p/${pid}/timeline`, "timeline", "الخط الزمني")}
            {link(`/p/${pid}/graph`, "graph", "شبكة العلاقات")}
            {link(`/p/${pid}/continuity`, "continuity", "الاستمرارية",
              openConf ? <span className={`badge ${highConf ? "bad" : "warn"}`}>{openConf}</span> : null)}
            <div className="nav-section">البحث والذكاء</div>
            {link(`/p/${pid}/sources`, "sources", "المصادر والشواهد")}
            {link(`/p/${pid}/agents`, "agents", "غرفة الوكلاء")}
            {link(`/p/${pid}/proposals`, "proposals", "المقترحات والنقد",
              d?.pending_proposals ? <span className="badge gold">{d.pending_proposals}</span> : null)}
            {link(`/p/${pid}/insight`, "insight", "البصمة والتقييم")}
            <div className="nav-section">الإخراج</div>
            {link(`/p/${pid}/publish`, "publish", "التصدير والنشر")}
            {link(`/p/${pid}/settings`, "settings", "الإعدادات والخصوصية")}
          </>
        )}
      </nav>
      <main className={`main ${flush ? "flush" : ""}`} id="main">
        {project && proj.isLoading ? <Loading /> : project && proj.isError ? <Navigate to="/" replace /> : children}
      </main>
    </div>
  );
}

export function roleLabel(r?: string | null) {
  return ({ owner: "صاحب الرواية", editor: "محرر", commenter: "معلّق", reader: "قارئ تجريبي" } as Record<string, string>)[r || ""] || "";
}
