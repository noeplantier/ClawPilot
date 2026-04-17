import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Campaigns from "@/pages/Campaigns";
import Leads from "@/pages/Leads";
import Agents from "@/pages/Agents";
import Messages from "@/pages/Messages";
import Analytics from "@/pages/Analytics";
import Settings from "@/pages/Settings";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen bg-[#050505] flex items-center justify-center text-[#8B949E] font-mono mono-accent">// booting.command.center</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function Public({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) return <Navigate to="/app/dashboard" replace />;
  return children;
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <Toaster theme="dark" position="top-right" toastOptions={{ style: { background: "#0A0A0A", border: "1px solid #262626", color: "#F8FAFC", fontFamily: "IBM Plex Sans" } }} />
          <Routes>
            <Route path="/" element={<Navigate to="/app/dashboard" replace />} />
            <Route path="/login" element={<Public><Login /></Public>} />
            <Route path="/register" element={<Public><Register /></Public>} />
            <Route path="/app" element={<Protected><Layout /></Protected>}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="campaigns" element={<Campaigns />} />
              <Route path="leads" element={<Leads />} />
              <Route path="agents" element={<Agents />} />
              <Route path="messages" element={<Messages />} />
              <Route path="analytics" element={<Analytics />} />
              <Route path="settings" element={<Settings />} />
            </Route>
            <Route path="*" element={<Navigate to="/app/dashboard" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
