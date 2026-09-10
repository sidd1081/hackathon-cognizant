import { Spinner } from "./Spinner.jsx";

const VARIANTS = {
  primary:
    "bg-violet-600 text-white hover:bg-violet-500 focus-visible:ring-violet-500 shadow-sm",
  secondary:
    "bg-transparent text-[#8b949e] border border-[#30363d] hover:border-[#6e7681] hover:text-[#e6edf3] focus-visible:ring-[#6e7681]",
};

export function Button({ variant = "primary", loading = false, disabled = false, className = "", children, ...props }) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0d1117] disabled:cursor-not-allowed disabled:opacity-40";
  return (
    <button className={`${base} ${VARIANTS[variant]} ${className}`} disabled={disabled || loading} {...props}>
      {loading && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  );
}
