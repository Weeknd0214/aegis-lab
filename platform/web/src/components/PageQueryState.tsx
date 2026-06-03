import React from "react";

interface PageQueryStateProps {
  loading: boolean;
  error?: string | null;
  empty?: boolean;
  emptyMessage?: string;
  children: React.ReactNode;
}

export const PageQueryState: React.FC<PageQueryStateProps> = ({
  loading,
  error,
  empty,
  emptyMessage = "暂无数据",
  children,
}) => {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-gray-400 text-sm animate-pulse">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-red-500 text-sm">加载失败: {error}</div>
      </div>
    );
  }

  if (empty) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-gray-400 text-sm">{emptyMessage}</div>
      </div>
    );
  }

  return <>{children}</>;
};
