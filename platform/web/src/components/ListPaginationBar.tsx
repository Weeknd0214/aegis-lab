import React from "react";

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

interface ListPaginationBarProps {
  total: number;
  offset: number;
  limit: number;
  onOffsetChange: (offset: number) => void;
  onLimitChange: (limit: number) => void;
}

export const ListPaginationBar: React.FC<ListPaginationBarProps> = ({
  total,
  offset,
  limit,
  onOffsetChange,
  onLimitChange,
}) => {
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);

  return (
    <div className="flex items-center justify-between pt-3 text-sm text-gray-500">
      <div>
        共 {total} 条，显示 {start}–{end}
      </div>
      <div className="flex items-center gap-2">
        <select
          value={limit}
          onChange={(e) => onLimitChange(Number(e.target.value))}
          className="border border-gray-300 rounded px-2 py-1 text-xs"
        >
          {PAGE_SIZE_OPTIONS.map((s) => (
            <option key={s} value={s}>{s}条/页</option>
          ))}
        </select>
        <button
          disabled={page <= 1}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
          className="px-2 py-1 border border-gray-300 rounded disabled:opacity-30 hover:bg-gray-50"
        >
          ‹ 上一页
        </button>
        <span className="text-xs">{page}/{totalPages}</span>
        <button
          disabled={page >= totalPages}
          onClick={() => onOffsetChange(offset + limit)}
          className="px-2 py-1 border border-gray-300 rounded disabled:opacity-30 hover:bg-gray-50"
        >
          下一页 ›
        </button>
      </div>
    </div>
  );
};
