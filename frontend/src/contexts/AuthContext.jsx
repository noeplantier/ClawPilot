import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

const DEMO_EMAIL = "demo@clawpilot.io";
const DEMO_PASSWORD = "Demo12345!";
const DEMO_TOKEN = "bypass-token-12345";

const DEMO_USER_DATA = {
  user: { id: "demo-1", email: DEMO_EMAIL, name: "Operator" },
  organization: { id: "org-1", name: "ClawPilot Demo" }
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [org, setOrg] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    const token = localStorage.getItem("openclaw_token");
    if (!token) { 
      setLoading(false); 
      return; 
    }

    // Interception pour le mode Démo
    if (token === DEMO_TOKEN) {
      setUser(DEMO_USER_DATA.user);
      setOrg(DEMO_USER_DATA.organization);
      setLoading(false);
      return;
    }

    try {
      const { data } = await api.get("/auth/me");
      setUser(data.user);
      setOrg(data.organization);
    } catch (e) {
      localStorage.removeItem("openclaw_token");
      setUser(null);
      setOrg(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadMe(); }, [loadMe]);

  const login = async (email, password) => {
    // Interception pour le mode Démo
    if (email === DEMO_EMAIL && password === DEMO_PASSWORD) {
      localStorage.setItem("openclaw_token", DEMO_TOKEN);
      setUser(DEMO_USER_DATA.user);
      setOrg(DEMO_USER_DATA.organization);
      return { access_token: DEMO_TOKEN, ...DEMO_USER_DATA };
    }

    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("openclaw_token", data.access_token);
    setUser(data.user);
    setOrg(data.organization);
    return data;
  };

  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    localStorage.setItem("openclaw_token", data.access_token);
    setUser(data.user);
    setOrg(data.organization);
    return data;
  };

  const logout = () => {
    localStorage.removeItem("openclaw_token");
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