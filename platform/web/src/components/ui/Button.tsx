import React from "react";

type ButtonVariant = "primary" | "default" | "danger" | "success" | "ghost";
type ButtonSize = "small" | "medium" | "large";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  look?: string;
  loading?: boolean;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-blue-700 text-white hover:bg-blue-800 active:bg-blue-900",
  default: "bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 active:bg-gray-100",
  danger: "bg-red-600 text-white hover:bg-red-700 active:bg-red-800",
  success: "bg-green-600 text-white hover:bg-green-700 active:bg-green-800",
  ghost: "bg-transparent text-gray-600 hover:bg-gray-100 active:bg-gray-200",
};

const sizeClasses: Record<ButtonSize, string> = {
  small: "px-3 py-1.5 text-xs rounded",
  medium: "px-4 py-2 text-sm rounded-md",
  large: "px-6 py-3 text-base rounded-md",
};

export const Button: React.FC<ButtonProps> = ({
  variant = "default",
  size = "medium",
  look,
  loading,
  className = "",
  disabled,
  children,
  ...props
}) => {
  // Map legacy "look" prop to variant
  const resolvedVariant = (look === "primary" ? "primary" : look === "danger" ? "danger" : variant) as ButtonVariant;

  const cls = [
    "inline-flex items-center justify-center font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500/30 disabled:opacity-50 disabled:cursor-not-allowed",
    variantClasses[resolvedVariant],
    sizeClasses[size],
    className,
  ].join(" ");

  return (
    <button className={cls} disabled={disabled || loading} {...props}>
      {loading && (
        <span className="mr-2 inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
      )}
      {children}
    </button>
  );
};
