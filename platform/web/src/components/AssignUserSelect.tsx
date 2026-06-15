import React, { useEffect, useMemo, useRef, useState } from "react";
import { Userpic } from "@/components/ui/Userpic";

export interface AssigneeOption {
  id: number;
  name: string;
  avatar_url?: string;
  department_names?: string[];
}

const triggerClass =
  "h-10 w-full flex items-center gap-2 px-2.5 text-sm border border-gray-200 rounded-lg bg-white text-left transition-colors outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-500/10";

interface AssignUserSelectProps {
  value: number;
  options: AssigneeOption[];
  excludedIds: number[];
  onChange: (userId: number) => void;
  placeholder?: string;
  disabled?: boolean;
}

export const AssignUserSelect: React.FC<AssignUserSelectProps> = ({
  value,
  options,
  excludedIds,
  onChange,
  placeholder = "选择成员",
  disabled = false,
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.id === value);

  const available = useMemo(() => {
    const q = query.trim().toLowerCase();
    return options
      .filter((o) => !excludedIds.includes(o.id) || o.id === value)
      .filter((o) => {
        if (!q) return true;
        if (o.name.toLowerCase().includes(q)) return true;
        return (o.department_names || []).some((d) => d.toLowerCase().includes(q));
      });
  }, [options, excludedIds, value, query]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  return (
    <div ref={rootRef} className="relative w-40 shrink-0">
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        className={`${triggerClass} ${
          disabled
            ? "border-gray-100 text-gray-400 cursor-not-allowed"
            : open
              ? "border-blue-400 ring-2 ring-blue-500/10"
              : "hover:border-gray-300"
        }`}
      >
        {selected ? (
          <>
            <Userpic username={selected.name} avatarUrl={selected.avatar_url} size={22} />
            <span className="flex-1 min-w-0 font-medium text-gray-800 truncate">{selected.name}</span>
          </>
        ) : (
          <span className="flex-1 text-gray-400 truncate">{placeholder}</span>
        )}
        <svg
          className={`w-3.5 h-3.5 text-gray-400 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute z-50 mt-1 left-0 w-64 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden">
          <div className="p-2 border-b border-gray-100 bg-gray-50/80">
            <input
              autoFocus
              className="h-9 w-full px-3 text-sm border border-gray-200 rounded-lg outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-500/10 bg-white"
              placeholder="搜索姓名或部门..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <ul className="max-h-52 overflow-y-auto py-1">
            {available.length === 0 ? (
              <li className="px-4 py-5 text-center text-sm text-gray-400">无匹配成员</li>
            ) : (
              available.map((u) => (
                <li key={u.id}>
                  <button
                    type="button"
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors ${
                      u.id === value ? "bg-blue-50 text-blue-800" : "hover:bg-gray-50 text-gray-700"
                    }`}
                    onClick={() => {
                      onChange(u.id);
                      setOpen(false);
                      setQuery("");
                    }}
                  >
                    <Userpic username={u.name} avatarUrl={u.avatar_url} size={28} />
                    <span className="flex-1 min-w-0 text-left truncate font-medium">{u.name}</span>
                    {u.id === value && (
                      <svg className="w-3.5 h-3.5 text-blue-600 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    )}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
};
