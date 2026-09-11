import { useState } from "react";
import { Button } from "./ui/Button.jsx";
import { Alert } from "./ui/Alert.jsx";

const FIELD_CLASS =
  "mt-1 w-full rounded-lg border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm text-[#e6edf3] placeholder:text-[#6e7681] focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/40";

function FormInput({ id, label, type, value, onChange, placeholder, autoComplete, minLength, required = true }) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-[#8b949e]">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type={type}
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
        placeholder={placeholder}
        minLength={minLength}
        className={FIELD_CLASS}
        required={required}
      />
    </div>
  );
}

export function AuthPage({ onLogin, onSignup }) {
  const [mode, setMode] = useState("login");
  const [formData, setFormData] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const isSignup = mode === "signup";

  const handleChange = (e) => {
    const { id, value } = e.target;
    setFormData((prev) => ({ ...prev, [id]: value }));
  };

  const switchMode = () => {
    setMode((prev) => (prev === "signup" ? "login" : "signup"));
    setError("");
    setFormData({ name: "", email: "", password: "" });
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);

    try {
      if (isSignup) {
        await onSignup(formData.name, formData.email, formData.password);
      } else {
        await onLogin(formData.email, formData.password);
      }
    } catch (err) {
      setError(err?.message || "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0d1117] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-violet-600 text-sm font-bold text-white shadow-lg">
            RCA
          </div>
          <h1 className="mt-3 text-xl font-bold text-[#e6edf3]">AI Incident RCA Assistant</h1>
          <p className="mt-1 text-sm text-[#6e7681]">
            {isSignup ? "Create your account" : "Sign in to continue"}
          </p>
        </div>

        <form onSubmit={submit} className="space-y-4 rounded-xl border border-[#30363d] bg-[#161b22] p-6">
          {isSignup && (
            <FormInput
              id="name"
              label="Name"
              type="text"
              value={formData.name}
              onChange={handleChange}
              autoComplete="name"
              placeholder="Jane Doe"
            />
          )}

          <FormInput
            id="email"
            label="Email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            autoComplete={isSignup ? "email" : "username"}
            placeholder="you@example.com"
          />

          <FormInput
            id="password"
            label="Password"
            type="password"
            value={formData.password}
            onChange={handleChange}
            autoComplete={isSignup ? "new-password" : "current-password"}
            placeholder={isSignup ? "Min 8 characters" : "••••••••"}
            minLength={isSignup ? 8 : undefined}
          />

          {error && <Alert variant="error">{error}</Alert>}

          <Button type="submit" loading={busy} disabled={busy} className="w-full">
            {isSignup ? "Create Account" : "Sign In"}
          </Button>
        </form>

        <p className="mt-4 text-center text-xs text-[#6e7681]">
          {isSignup ? "Already have an account?" : "Don't have an account?"}{" "}
          <button type="button" onClick={switchMode} className="font-medium text-violet-400 hover:text-violet-300">
            {isSignup ? "Sign in" : "Sign up"}
          </button>
        </p>
      </div>
    </div>
  );
}
