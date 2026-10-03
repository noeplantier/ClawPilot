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
import Prospects from "@/pages/Prospects";
import ProspectDetail from "@/pages/ProspectDetail";
import ReviewQueue from "@/pages/ReviewQueue";
import Sending from "@/pages/Sending";
import Legal from "@/pages/legal/Legal";
import Privacy from "@/pages/legal/Privacy";
import Terms from "@/pages/legal/Terms";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen bg-[#EDEBE0] grid-bg flex items-center justify-center text-[#DC2626] font-mono mono-accent">// booting.command.center</div>;
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
          <Toaster theme="light" position="top-right" toastOptions={{ style: { background: "#FFFFFF", border: "1px solid #D6D3C8", color: "#0A0A0A", fontFamily: "IBM Plex Sans" } }} />
          <Routes>
            <Route path="/" element={<Navigate to="/app/dashboard" replace />} />
            <Route path="/legal" element={<Legal />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/login" element={<Public><Login /></Public>} />
            <Route path="/register" element={<Public><Register /></Public>} />
            <Route path="/app" element={<Protected><Layout /></Protected>}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="campaigns" element={<Campaigns />} />
              <Route path="leads" element={<Leads />} />
              <Route path="prospects" element={<Prospects />} />
              <Route path="prospects/review" element={<ReviewQueue />} />
              <Route path="prospects/:id" element={<ProspectDetail />} />
              <Route path="sending" element={<Sending />} />
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
