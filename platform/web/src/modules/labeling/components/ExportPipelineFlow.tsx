import React from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";

type ExportPipelineFlowProps = {
  pendingExport?: number;
  pendingBuild?: number;
};

const Arrow: React.FC<{ className?: string }> = ({ className = "" }) => (
  <div className={`flex items-center justify-center shrink-0 text-gray-300 ${className}`} aria-hidden>
    <svg className="w-3.5 h-3.5 hidden lg:block" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
    </svg>
    <svg className="w-3.5 h-3.5 lg:hidden" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
    </svg>
  </div>
);

type StepProps = {
  step: number;
  title: string;
  subtitle: string;
  role: string;
  badge?: React.ReactNode;
  icon: React.ReactNode;
  highlight?: "current" | "done" | "upstream";
  link?: string;
  footnote?: string;
};

const StepCard: React.FC<StepProps> = ({ step, title, subtitle, role, badge, icon, highlight = "upstream", link, footnote }) => {
  const shell =
    highlight === "current"
      ? "border-amber-200 bg-gradient-to-br from-amber-50/90 to-orange-50/50 shadow-sm ring-1 ring-amber-100"
      : highlight === "done"
        ? "border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-teal-50/40 ring-1 ring-emerald-100"
        : "border-gray-200 bg-gray-50/60";

  const content = (
    <div className={`relative flex flex-col rounded-xl border p-3 min-h-[6.75rem] flex-1 min-w-0 transition-shadow hover:shadow-md ${shell}`}>
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span
          className={`inline-flex h-5 w-5 items-center justify-center rounded-md text-[10px] font-bold ${
            highlight === "current"
              ? "bg-amber-500 text-white"
              : highlight === "done"
                ? "bg-emerald-500 text-white"
                : "bg-gray-200 text-gray-600"
          }`}
        >
          {step}
        </span>
        <span className="text-xs leading-none opacity-75 select-none">{icon}</span>
      </div>
      <h3 className="text-sm font-semibold text-gray-900 m-0">{title}</h3>
      <p className="text-[11px] text-gray-500 mt-1 leading-relaxed flex-1">{subtitle}</p>
      <div className="flex flex-wrap items-center gap-1.5 mt-2 pt-2 border-t border-black/5">
        <span className="text-[10px] uppercase tracking-wide text-gray-400 font-medium">{role}</span>
        {badge}
      </div>
      {footnote && <p className="text-[10px] text-gray-400 mt-1.5 m-0">{footnote}</p>}
    </div>
  );

  if (link) {
    return (
      <Link to={link} className="flex-1 min-w-[9rem] max-w-[14rem] no-underline text-inherit group">
        <div className="group-hover:scale-[1.02] transition-transform">{content}</div>
      </Link>
    );
  }
  return <div className="flex-1 min-w-[9rem] max-w-[14rem]">{content}</div>;
};

export const ExportPipelineFlow: React.FC<ExportPipelineFlowProps> = ({
  pendingExport = 0,
  pendingBuild = 0,
}) => {
  return (
    <div className="mb-4 rounded-2xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      <div className="px-4 py-3 border-b border-gray-100 bg-gradient-to-r from-slate-50 to-white flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-gray-800 m-0">送标 → 入库 全流程</h2>
          <p className="text-xs text-gray-500 m-0 mt-0.5">本页负责第 3、4 步；前两步在其他模块完成</p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {pendingExport > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 text-amber-800 px-2.5 py-1 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              {pendingExport} 待导出
            </span>
          )}
          {pendingBuild > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-orange-100 text-orange-800 px-2.5 py-1 font-medium">
              {pendingBuild} 待 build
            </span>
          )}
        </div>
      </div>

      <div className="p-4 lg:p-5">
        <div className="flex flex-col lg:flex-row lg:items-stretch gap-1 lg:gap-0">
          <StepCard
            step={1}
            title="提交质检"
            subtitle="标注员在标注进度页完成标注后提交"
            role="标注员"
            icon="📝"
            highlight="upstream"
            link="/labeling/campaigns"
            badge={<Badge variant="default" size="small">标注进度</Badge>}
          />
          <Arrow className="py-1 lg:py-0 lg:px-1" />
          <StepCard
            step={2}
            title="质检通过"
            subtitle="协调员审核合格/可用，退回则返工"
            role="协调员"
            icon="✓"
            highlight="upstream"
            link="/labeling/review"
            badge={<Badge variant="warning" size="small">待导出</Badge>}
          />
          <Arrow className="py-1 lg:py-0 lg:px-1" />
          <StepCard
            step={3}
            title="执行导出"
            subtitle="CVAT → 训练格式（DMS·YOLO / ADAS·quaternion_json）"
            role="本页操作"
            icon="📤"
            highlight="current"
            badge={<Badge variant="warning" size="small">待 build</Badge>}
            footnote={pendingExport > 0 ? `下方 ${pendingExport} 个批次可导出` : undefined}
          />
          <Arrow className="py-1 lg:py-0 lg:px-1" />
          <StepCard
            step={4}
            title="提交 build"
            subtitle="审核队列批准后 merge 进训练包"
            role="审核员"
            icon="🏗"
            highlight="done"
            badge={<Badge variant="success" size="small">已入库</Badge>}
            footnote="待 build ≠ 已入库"
          />
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-slate-50 border border-slate-100 px-3 py-2.5 text-[11px] text-gray-500">
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-gray-300" />
            上游步骤（可点击跳转）
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            本页：格式转换 / 供应商回标
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            终点：ingested 不再显示于本列表
          </span>
          <Link to="/system/audit" className="ml-auto text-blue-600 hover:underline font-medium">
            审核队列 →
          </Link>
        </div>
      </div>
    </div>
  );
};
