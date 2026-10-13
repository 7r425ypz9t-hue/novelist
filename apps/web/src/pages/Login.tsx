import { FormEvent, useState } from "react";
import { api, setToken } from "../api/client";
import { BrandMark } from "../components/Icon";
import { Field } from "../components/ui";

export function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api<{ token: string }>(`/v1/auth/${mode}`, {
        body: mode === "login" ? { email, password } : { email, password, display_name: name },
      });
      setToken(r.token, remember);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit} aria-labelledby="login-title">
        <div className="card-b stack" style={{ padding: 28 }}>
          <div style={{ textAlign: "center" }}>
            <span className="hero-ring" style={{ display: "inline-block" }}><BrandMark size={56} /></span>
            <h1 id="login-title">كاتب</h1>
            <p className="muted">مساحة الروائي العربي: كتابة، ذاكرة، تحقق، ونقد — والقرار الأخير لك.</p>
          </div>
          {mode === "register" && (
            <Field label="الاسم الظاهر"><input className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></Field>
          )}
          <Field label="البريد الإلكتروني">
            <input className="input" type="email" dir="ltr" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          </Field>
          <Field label="كلمة المرور">
            <input className="input" type="password" dir="ltr" required minLength={mode === "register" ? 10 : 1} value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </Field>
          {mode === "register" && <div className="dim">عشرة أحرف على الأقل. أول حساب على الخادم يصبح مسؤول النظام.</div>}
          <label className="check"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> تذكّرني على هذا الجهاز</label>
          {error && <div className="alert bad" role="alert">{error}</div>}
          <button className="btn primary" disabled={busy} style={{ justifyContent: "center", height: 38 }}>
            {mode === "login" ? "دخول" : "إنشاء حساب"}
          </button>
          <button type="button" className="btn ghost" style={{ justifyContent: "center" }} onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "ليس لديك حساب؟ أنشئ حساباً" : "لديك حساب؟ سجّل الدخول"}
          </button>
        </div>
      </form>
    </div>
  );
}
