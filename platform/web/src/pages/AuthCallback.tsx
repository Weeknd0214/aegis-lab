import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";

export function AuthCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const token = params.get("token");
    if (token) {
      localStorage.setItem("as_access_token", token);
      api.setToken(token);
      navigate("/labeling", { replace: true });
      window.location.reload();
    } else {
      navigate("/login", { replace: true });
    }
  }, [params, navigate]);

  return <p className="empty-state">登录处理中…</p>;
}
