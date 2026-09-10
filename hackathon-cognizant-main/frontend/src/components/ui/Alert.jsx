const STYLES = {
  error:   "border-red-700/50 bg-red-900/20 text-red-300",
  info:    "border-blue-700/40 bg-blue-900/20 text-blue-300",
  success: "border-emerald-700/40 bg-emerald-900/20 text-emerald-300",
};

export function Alert({ variant = "error", title, children }) {
  return (
    <div role="alert" className={`rounded-lg border px-4 py-3 text-sm ${STYLES[variant]}`}>
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={title ? "mt-0.5 opacity-80" : ""}>{children}</div>}
    </div>
  );
}
