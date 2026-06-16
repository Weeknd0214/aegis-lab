import React from "react";

interface TruncatedTextProps {
  text: string;
  className?: string;
  maxWidthClass?: string;
}

export const TruncatedText: React.FC<TruncatedTextProps> = ({
  text,
  className = "",
  maxWidthClass = "max-w-[12rem]",
}) => {
  if (!text) return <span className={`${className} text-center`}>—</span>;
  return (
    <span
      className={`block truncate cursor-default text-center mx-auto ${maxWidthClass} ${className}`}
      title={text}
    >
      {text}
    </span>
  );
};
