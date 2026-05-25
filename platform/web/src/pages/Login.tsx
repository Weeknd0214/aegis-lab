import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { user, loginFeishu, loginDev, authConfig } = useAuth();
  const navigate = useNavigate();
  const [err, setErr] = useState("");
  const [name, setName] = useState("开发用户");

  useEffect(() => {
    if (user) navigate("/labeling", { replace: true });
  }, [user, navigate]);

  const onDevLogin = async () => {
    setErr("");
    try {
      await loginDev(name);
      navigate("/labeling");
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <div className="login-page">
      <div className="login-shell simple">
        <section className="login-card panel" id="access">
          <h2>欢迎登录</h2>
          <p className="text-dim">广东华胥智能技术 · 卡车主动安全 AEB 平台</p>

          {authConfig?.feishu_enabled && (
            <button type="button" className="btn btn-primary btn-feishu" onClick={loginFeishu}>
              立即使用飞书登录
            </button>
          )}
          {authConfig?.dev_auth_enabled && (
            <div className="dev-login">
              <p className="text-sm text-dim">开发模式（未配置飞书 App）</p>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="显示名称" />
              <button type="button" className="btn btn-ghost" onClick={onDevLogin}>开发登录</button>
            </div>
          )}
          {!authConfig?.feishu_enabled && !authConfig?.dev_auth_enabled && (
            <p className="empty-state">当前未启用可用登录方式，请联系管理员。</p>
          )}
          {err && <p className="login-err">{err}</p>}
        </section>
      </div>
    </div>
  );
}
