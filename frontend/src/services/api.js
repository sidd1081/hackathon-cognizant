// All backend communication lives here. The frontend never holds the Groq key —
// analysis happens server-side; this module only calls the backend HTTP API.

// Backend base URL: in development or when configured, talk to local backend;
// in production default to deployed Cloud Run URL if not overridden.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL !== undefined && import.meta.env.VITE_API_BASE_URL !== ""
    ? import.meta.env.VITE_API_BASE_URL
    : (import.meta.env.DEV ? "http://127.0.0.1:8000" : "https://incident-rca-api-thamtf7d5a-uc.a.run.app");

// --- auth token storage ------------------------------------------------------
const TOKEN_KEY = "rca.auth.token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore storage errors (e.g. private mode) */
  }
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Turn a backend error payload into a readable message.
 * The backend returns `detail` as either a string, a Pydantic 422 array, or a
 * `{ message, errors[] }` object (dataset validation).
 */
function extractErrorMessage(payload, status) {
  if (payload && typeof payload === "object") {
    const detail = "detail" in payload ? payload.detail : payload;

    if (typeof detail === "string") return detail;

    if (Array.isArray(detail)) {
      const msgs = detail
        .map((e) => (e && e.msg ? e.msg : null))
        .filter(Boolean);
      if (msgs.length) return msgs.join("; ");
    }

    if (detail && typeof detail === "object") {
      const errors = Array.isArray(detail.errors) ? detail.errors : [];
      if (detail.message) {
        return errors.length
          ? `${detail.message} ${errors.join("; ")}`
          : detail.message;
      }
      if (errors.length) return errors.join("; ");
    }
  }
  return `Request failed (HTTP ${status}).`;
}

async function request(path, options = {}) {
  const headers = { ...authHeaders(), ...(options.headers || {}) };
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new Error(
      "Could not reach the server. Is the backend running on the expected port?",
    );
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => null);

  if (!response.ok) {
    throw new Error(extractErrorMessage(payload, response.status));
  }
  return payload;
}

/** POST /api/incidents/analyze */
export function analyzeIncident(description) {
  return request("/api/incidents/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description }),
  });
}

/** POST /api/dataset/upload (multipart) */
export function uploadDataset(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/dataset/upload", { method: "POST", body: form });
}

/** GET /api/health */
export function getHealth() {
  return request("/api/health", { method: "GET" });
}

/** GET /api/evaluation */
export function getEvaluation() {
  return request("/api/evaluation", { method: "GET" });
}

/** POST /api/auth/signup → { access_token, user } */
export function signup(name, email, password) {
  return request("/api/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
}

/** POST /api/auth/login → { access_token, user } */
export function login(email, password) {
  return request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

/** GET /api/auth/me → user (requires token) */
export function getMe() {
  return request("/api/auth/me", { method: "GET" });
}
