import { useCallback, useState } from "react";
import {
  getToken,
  setToken,
  login as apiLogin,
  signup as apiSignup,
} from "../services/api.js";

// Real auth backed by the API: signup/login return a JWT that is stored in
// localStorage (see services/api.js) and attached to subsequent requests. The
// user profile is cached alongside it so the session survives a page refresh.
const USER_KEY = "rca.auth.user";

function readUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function useAuth() {
  const [user, setUser] = useState(() => (getToken() ? readUser() : null));

  const persist = useCallback((data) => {
    setToken(data.access_token);
    try {
      localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    } catch {
      /* ignore */
    }
    setUser(data.user);
  }, []);

  const login = useCallback(
    async (email, password) => persist(await apiLogin(email, password)),
    [persist],
  );

  const signup = useCallback(
    async (name, email, password) =>
      persist(await apiSignup(name, email, password)),
    [persist],
  );

  const logout = useCallback(() => {
    setToken(null);
    try {
      localStorage.removeItem(USER_KEY);
    } catch {
      /* ignore */
    }
    setUser(null);
  }, []);

  return { user, isAuthenticated: Boolean(user), login, signup, logout };
}
