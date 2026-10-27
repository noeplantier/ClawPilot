import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Layout from "@/components/Layout";
import { pages } from "@/lib/routes";
const Dashboard = lazy(pages.dashboard);
const Campaigns = lazy(pages.campaigns);
const Leads = lazy(pages.leads);
const Agents = lazy(pages.agents);
const Messages = lazy(pages.messages);
const Analytics = lazy(pages.analytics);
const Settings = lazy(pages.settings);
const Prospects = lazy(pages.prospects);
const MapSearch = lazy(pages.map);
const Sources = lazy(pages.sources);
const SystemHealth = lazy(pages.system);
const ProspectDetail = lazy(pages.prospectDetail);
const ReviewQueue = lazy(pages.review);
const Sending = lazy(pages.sending);
const ProspectImport = lazy(pages.prospectImport);
const Legal = lazy(() => import("@/pages/legal/Legal"));
const Privacy = lazy(() => import("@/pages/legal/Privacy"));
const Terms = lazy(() => import("@/pages/legal/Terms"));

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen bg-[#E9EEF7] grid-bg flex items-center justify-center text-[#4F46E5] font-mono mono-accent">// booting.command.center</div>;
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
          <Toaster theme="light" position="top-right" toastOptions={{ style: { background: "#FFFFFF", border: "1px solid #D3DBEA", color: "#0A0A0A", fontFamily: "IBM Plex Sans" } }} />
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
              <Route path="sources" element={<Sources />} />
              <Route path="system" element={<SystemHealth />} />
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
