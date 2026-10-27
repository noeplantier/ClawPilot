import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import * as swr from "@/lib/swr";

const AuthContext = createContext(null);
const TOKEN = "outreachos_token";
const SESSION = "outreachos_session"; // who is signed in, kept to paint the app at once: the server confirms it right after

const readSession = () => {
  try {
    const s = JSON.parse(localStorage.getItem(SESSION) || "null");
    return s && s.user && s.organization ? s : null;
  } catch {
    return null;
  }
};
const writeSession = (user, organization) => {
  try { localStorage.setItem(SESSION, JSON.stringify({ user, organization })); } catch { /* storage blocked: only the paint-at-once is lost */ }
};

export function AuthProvider({ children }) {
  // A signed-in person who comes back sees the app immediately, not a boot screen while a sleeping API wakes up: the cached
  // identity is shown, then replaced by the server's answer. A 401 (api.js) still ends the session.
  const [cached] = useState(() => (localStorage.getItem(TOKEN) ? readSession() : null));
  const [user, setUser] = useState(cached ? cached.user : null);
  const [org, setOrg] = useState(cached ? cached.organization : null);
  const [loading, setLoading] = useState(!cached);

  const loadMe = useCallback(async () => {
    const token = localStorage.getItem(TOKEN);
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data.user);
      setOrg(data.organization);
      writeSession(data.user, data.organization);
    } catch (e) {
      // Only a refused token ends the session (and api.js has already cleared it). An unreachable or waking API keeps it.
      if (e?.response?.status === 401) {
        localStorage.removeItem(TOKEN);
        localStorage.removeItem(SESSION);
        setUser(null);
        setOrg(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadMe(); }, [loadMe]);

  const start = (data) => {
    localStorage.setItem(TOKEN, data.access_token);
    writeSession(data.user, data.organization);
    setUser(data.user);
    setOrg(data.organization);
    return data;
  };

  const login = async (email, password) => start((await api.post("/auth/login", { email, password })).data);

  const register = async (payload) => start((await api.post("/auth/register", payload)).data);

  const logout = () => {
    localStorage.removeItem(TOKEN);
    localStorage.removeItem(SESSION);
    swr.clear(); // the next person on this browser must not see this organisation's cached data
    setUser(null);
    setOrg(null);
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider value={{ user, org, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
