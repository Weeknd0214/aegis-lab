import React, { useState } from "react";
import { useAuth } from "@/app/AuthContext";
import { Button } from "@/components/ui/Button";

const LOGIN_BG = "/login-bg.png";

export const LoginPage: React.FC = () => {
  const { authConfig, loginDev, loginFeishu, loading } = useAuth();
  const [devName, setDevName] = useState("开发用户");
  const [loggingIn, setLoggingIn] = useState(false);

  const shellCls =
    "min-h-screen relative flex items-center justify-end bg-cover bg-center bg-no-repeat px-6 py-10 md:px-16";

  if (loading) {
    return (
      <div className={shellCls} style={{ backgroundImage: `url(${LOGIN_BG})` }}>
        <div className="absolute inset-0 bg-slate-900/25" />
        <div className="relative z-10 text-white/90 animate-pulse">加载中...</div>
      </div>
    );
  }

  return (
    <div className={shellCls} style={{ backgroundImage: `url(${LOGIN_BG})` }}>
      <div className="absolute inset-0 bg-gradient-to-l from-slate-900/55 via-slate-900/20 to-transparent" />

      <div className="relative z-10 w-full max-w-md rounded-2xl border border-white/20 bg-white/92 backdrop-blur-md shadow-2xl p-8">
        <div className="mb-6">
          <p className="text-xs font-medium tracking-widest text-blue-600 uppercase">HSAP Platform</p>
          <h1 className="text-2xl font-bold text-gray-900 mt-1">华胥 Sentinel</h1>
          <p className="text-sm text-gray-500 mt-1">主动安全算法迭代平台</p>
        </div>

        {authConfig?.feishu_enabled && (
          <Button variant="primary" className="w-full mb-3" onClick={loginFeishu}>
            飞书账号登录
          </Button>
        )}

        {authConfig?.dev_auth_enabled && (
          <div className="border-t border-gray-200 pt-4 mt-4">
            <p className="text-xs text-gray-400 mb-2 text-center">开发模式</p>
            <input
              className="form-input mb-2"
              value={devName}
              onChange={(e) => setDevName(e.target.value)}
              placeholder="输入用户名"
            />
            <Button
              variant="default"
              className="w-full"
              loading={loggingIn}
              onClick={async () => {
                setLoggingIn(true);
                try {
                  await loginDev(devName);
                } catch {
                  // error handled by AuthContext
                }
                setLoggingIn(false);
              }}
            >
              开发登录
            </Button>
          </div>
        )}

        {!authConfig?.feishu_enabled && !authConfig?.dev_auth_enabled && (
          <p className="text-sm text-red-500 text-center">认证服务未配置</p>
        )}
      </div>
    </div>
  );
};
