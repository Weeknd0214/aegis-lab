import React from "react";

interface UserpicProps {
  username?: string;
  avatarUrl?: string;
  size?: number;
  className?: string;
}

export const Userpic: React.FC<UserpicProps> = ({
  username = "",
  avatarUrl,
  size = 32,
  className = "",
}) => {
  const initials = username
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() || "")
    .join("");

  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={username}
        width={size}
        height={size}
        className={`rounded-full object-cover ${className}`}
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <span
      className={`inline-flex items-center justify-center rounded-full bg-blue-100 text-blue-800 font-semibold ${className}`}
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {initials || "?"}
    </span>
  );
};
