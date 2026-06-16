import React from "react";

type ColWidth = string | number;

type CompactTableShellProps = {
  children: React.ReactNode;
  colWidths?: ColWidth[];
};

export const CompactTableShell: React.FC<CompactTableShellProps> = ({ children, colWidths }) => (
  <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
    <div className="overflow-hidden">
      <table className="table-auto table-fixed w-full min-w-0 [&_th]:py-1.5 [&_th]:px-2 [&_th]:text-center [&_td]:py-1.5 [&_td]:px-2 [&_td]:text-center">
        {colWidths && colWidths.length > 0 && (
          <colgroup>
            {colWidths.map((w, i) => (
              <col key={i} style={typeof w === "number" ? { width: w } : { width: w }} />
            ))}
          </colgroup>
        )}
        {children}
      </table>
    </div>
  </div>
);
