import React, { useState } from "react";
import { useAuth } from "@/app/AuthContext";
import { Button } from "@/components/ui/Button";

export const LoginPage: React.FC = () => {
  const { authConfig, loginDev, loginFeishu, loading } = useAuth();
  const [devName, setDevName] = useState("开发用户");
  const [loggingIn, setLoggingIn] = useState(false);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-gray-400 animate-pulse">加载中...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 w-full max-w-sm">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-gray-900">HSAP</h1>
          <p className="text-sm text-gray-500 mt-1">华胥 Sentinel 主动安全平台</p>
        </div>

        {/* Feishu login */}
        {authConfig?.feishu_enabled && (
          <Button
            variant="primary"
            className="w-full mb-3"
            onClick={loginFeishu}
          >
            飞书账号登录
          </Button>
        )}

        {/* Dev login */}
        {authConfig?.dev_auth_enabled && (
          <div className="border-t pt-4 mt-4">
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
