import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Layout from "@/components/Layout";
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Campaigns = lazy(() => import("@/pages/Campaigns"));
const Leads = lazy(() => import("@/pages/Leads"));
const Agents = lazy(() => import("@/pages/Agents"));
const Messages = lazy(() => import("@/pages/Messages"));
const Analytics = lazy(() => import("@/pages/Analytics"));
const Settings = lazy(() => import("@/pages/Settings"));
const Prospects = lazy(() => import("@/pages/Prospects"));
const MapSearch = lazy(() => import("@/pages/MapSearch"));
const ProspectDetail = lazy(() => import("@/pages/ProspectDetail"));
const ReviewQueue = lazy(() => import("@/pages/ReviewQueue"));
const Sending = lazy(() => import("@/pages/Sending"));
const ProspectImport = lazy(() => import("@/pages/ProspectImport"));
const Legal = lazy(() => import("@/pages/legal/Legal"));
const Privacy = lazy(() => import("@/pages/legal/Privacy"));
const Terms = lazy(() => import("@/pages/legal/Terms"));

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
          <Suspense fallback={<div className="p-10 font-mono mono-accent" role="status">// loading</div>}>
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
              <Route path="map" element={<MapSearch />} />
              <Route path="prospects/import" element={<ProspectImport />} />
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
          </Suspense>
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
