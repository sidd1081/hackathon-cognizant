import { useState } from "react";
import { Button } from "./ui/Button.jsx";
import { Alert } from "./ui/Alert.jsx";

const FIELD =
  "mt-1 w-full rounded-lg border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm text-[#e6edf3] placeholder:text-[#6e7681] focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/40";

export function AuthPage({ onLogin, onSignup }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const isSignup = mode === "signup";
  const switchMode = () => { setMode(isSignup ? "login" : "signup"); setError(""); };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (isSignup) await onSignup(name, email, password);
      else await onLogin(email, password);
    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.");
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
            <div>
              <label htmlFor="name" className="block text-xs font-medium text-[#8b949e]">Name</label>
              <input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)}
                autoComplete="name" placeholder="Jane Doe" className={FIELD} required />
            </div>
          )}
          <div>
            <label htmlFor="email" className="block text-xs font-medium text-[#8b949e]">Email</label>
            <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              autoComplete={isSignup ? "email" : "username"} placeholder="you@example.com" className={FIELD} required />
          </div>
          <div>
            <label htmlFor="password" className="block text-xs font-medium text-[#8b949e]">Password</label>
            <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete={isSignup ? "new-password" : "current-password"}
              placeholder={isSignup ? "Min 8 characters" : "••••••••"}
              minLength={isSignup ? 8 : undefined} className={FIELD} required />
          </div>

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
