import React from "react";
import { Button } from "@/components/ui/Button";

type DeliveryIntakePanelProps = {
  total: number;
  inLake: number;
  pending: number;
  scanPending?: number;
  scanning: boolean;
  canCreate: boolean;
  onScan: () => void;
  onCreate: () => void;
};

export const DeliveryIntakePanel: React.FC<DeliveryIntakePanelProps> = ({
  total,
  inLake,
  pending,
  scanPending,
  scanning,
  canCreate,
  onScan,
  onCreate,
}) => (
  <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
    <div className="card p-4 border-blue-100 bg-blue-50/40">
      <div className="text-xs text-blue-600 font-medium mb-1">台账总批次</div>
      <div className="text-2xl font-semibold text-blue-900 tabular-nums">{total}</div>
      <div className="text-xs text-gray-500 mt-1">已入湖 {inLake} · 待处理 {pending}</div>
    </div>

    <button
      type="button"
      onClick={onScan}
      className="card p-4 text-left border-emerald-100 bg-emerald-50/40 hover:border-emerald-300 transition-colors"
    >
      <div className="text-xs text-emerald-700 font-medium mb-1">① 扫描数据湖</div>
      <div className="text-sm font-semibold text-emerald-900">inbox 周期落盘</div>
      <div className="text-xs text-gray-500 mt-2">
        {scanPending != null ? `待登记 ${scanPending} 批` : "发现 inbox 新批次"}
      </div>
      <Button size="small" variant="primary" className="mt-3" loading={scanning} onClick={(e) => { e.stopPropagation(); onScan(); }}>
        立即扫描
      </Button>
    </button>

    <button
      type="button"
      disabled={!canCreate}
      onClick={onCreate}
      className="card p-4 text-left border-amber-100 bg-amber-50/40 hover:border-amber-300 transition-colors disabled:opacity-50"
    >
      <div className="text-xs text-amber-700 font-medium mb-1">② NAS 外挂送标</div>
      <div className="text-sm font-semibold text-amber-900">挂载盘 → 审批入湖</div>
      <div className="text-xs text-gray-500 mt-2">填写路径与采集周期</div>
      {canCreate && (
        <Button size="small" variant="default" className="mt-3" onClick={(e) => { e.stopPropagation(); onCreate(); }}>
          新建申请
        </Button>
      )}
    </button>

    <div className="card p-4 border-purple-100 bg-purple-50/40">
      <div className="text-xs text-purple-700 font-medium mb-1">③ 送标工作台</div>
      <div className="text-sm font-semibold text-purple-900">入湖后开标</div>
      <div className="text-xs text-gray-500 mt-2">台账登记 → 工作台待送标</div>
      <a href="/labeling/workbench" className="inline-block mt-3">
        <Button size="small" variant="default">去开标 →</Button>
      </a>
    </div>
  </div>
);
