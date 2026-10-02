import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [org, setOrg] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    const token = localStorage.getItem("clawpilot_token");
    if (!token) { 
      setLoading(false); 
      return; 
    }

    try {
      const { data } = await api.get("/auth/me");
      setUser(data.user);
      setOrg(data.organization);
    } catch (e) {
      localStorage.removeItem("clawpilot_token");
      setUser(null);
      setOrg(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadMe(); }, [loadMe]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("clawpilot_token", data.access_token);
    setUser(data.user);
    setOrg(data.organization);
    return data;
  };

  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    localStorage.setItem("clawpilot_token", data.access_token);
    setUser(data.user);
    setOrg(data.organization);
    return data;
  };

  const logout = () => {
    localStorage.removeItem("clawpilot_token");
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