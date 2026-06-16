import React from "react";

type FilterChip = { label: string; value: string };

type LabelingListToolbarProps = {
  search: string;
  onSearchChange: (value: string) => void;
  placeholder?: string;
  filters?: FilterChip[];
  filterValue?: string;
  onFilterChange?: (value: string) => void;
  total: number;
  extra?: React.ReactNode;
};

export const LabelingListToolbar: React.FC<LabelingListToolbarProps> = ({
  search,
  onSearchChange,
  placeholder = "搜索批次/任务/项目...",
  filters,
  filterValue = "",
  onFilterChange,
  total,
  extra,
}) => (
  <div className="bg-white rounded-xl border border-gray-200 p-3 mb-4">
    <div className="flex items-center gap-3 flex-wrap">
      <div className="flex-1 min-w-[200px] relative">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
          placeholder={placeholder}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>
      {filters && onFilterChange && (
        <div className="flex gap-1.5">
          {filters.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => onFilterChange(f.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filterValue === f.value ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}
      {extra}
      <span className="text-xs text-gray-500 font-medium bg-gray-50 px-2.5 py-1 rounded-full">{total} 条</span>
    </div>
  </div>
);
