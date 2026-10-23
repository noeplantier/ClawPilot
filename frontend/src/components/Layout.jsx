import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import {
  SquaresFour, Target, Users, Robot, ChatsCircle, ChartLine, Gear, SignOut, Lightning, MagnifyingGlass, Sparkle,
  ListChecks, PaperPlaneTilt, MapTrifold, Database, Heartbeat, CaretLeft, CaretRight,
} from "@phosphor-icons/react";
import AIComposerModal from "@/components/AIComposerModal";
import Footer from "@/components/Footer";
import { isTypingTarget, readPref, writePref } from "@/lib/uiPrefs";

const NAV = [
  { to: "/app/dashboard", icon: SquaresFour, label: "Dashboard" },
  { to: "/app/campaigns", icon: Target, label: "Campaigns" },
  { to: "/app/leads", icon: Users, label: "Leads CRM" },
  { to: "/app/sources", icon: Database, label: "Sources" },
  { to: "/app/map", icon: MapTrifold, label: "Map search" },
  { to: "/app/prospects", icon: MagnifyingGlass, label: "Prospects" },
  { to: "/app/prospects/review", icon: ListChecks, label: "Review queue" },
  { to: "/app/sending", icon: PaperPlaneTilt, label: "Sending" },
  { to: "/app/agents", icon: Robot, label: "Agents" },
  { to: "/app/messages", icon: ChatsCircle, label: "Messages" },
  { to: "/app/analytics", icon: ChartLine, label: "Analytics" },
  { to: "/app/system", icon: Heartbeat, label: "System health" },
  { to: "/app/settings", icon: Gear, label: "Settings" },
];

export default function Layout() {
  const { user, org, logout } = useAuth();
  const [aiOpen, setAiOpen] = useState(false);
  const [folded, setFolded] = useState(() => readPref("sidebar.folded", false));

  useEffect(() => writePref("sidebar.folded", folded), [folded]);

  // "[" folds or unfolds the sidebar (never while typing in a field).
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "[" && !isTypingTarget(e.target) && !e.ctrlKey && !e.metaKey && !e.altKey) setFolded((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const foldButton = (
    <button
      onClick={() => setFolded((v) => !v)}
      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-indigo-300/30 bg-white/5 text-cyan-300 hover:text-white hover:shadow-[0_0_12px_rgba(34,211,238,0.6)] transition ${folded ? "" : "ml-auto"}`}
      aria-label={folded ? "Unfold the sidebar" : "Fold the sidebar"}
      aria-expanded={!folded}
      title={folded ? "Unfold the sidebar ([)" : "Fold the sidebar ([)"}
      data-testid="sidebar-toggle"
    >
      {folded ? <CaretRight size={14} weight="bold" /> : <CaretLeft size={14} weight="bold" />}
    </button>
  );

  return (
    <div className="min-h-screen md:h-screen flex text-[#0A0A0A] grid-bg">
      {/* Sidebar */}
      <aside
        className={`hidden md:flex ${folded ? "w-[4.75rem]" : "w-64"} shrink-0 flex-col sticky top-0 h-screen text-slate-200 bg-gradient-to-b from-[#0B1020] via-[#0E1530] to-[#0B1020] border-r border-indigo-400/20 shadow-[4px_0_40px_-12px_rgba(79,70,229,0.45)] transition-[width] duration-300`}
        data-testid="sidebar"
        data-folded={folded}
        aria-label="Main navigation"
      >
        <div className={`relative ${folded ? "px-3 justify-center" : "px-5"} py-5 ${folded ? "" : "border-b border-white/10"} flex items-center gap-2`}>
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-violet-500 to-cyan-400 shadow-[0_0_20px_-2px_rgba(99,102,241,0.8)]">
            <Lightning size={18} weight="fill" className="text-white" />
          </span>
          {!folded && (
            <div className="min-w-0">
              <div className="font-display font-black tracking-tight text-base text-white leading-none">OUTREACHOS</div>
              <div className="font-mono text-[10px] tracking-[0.12em] text-cyan-300 mt-1 whitespace-nowrap">/// command.center</div>
            </div>
          )}
          {!folded && foldButton}
        </div>
        {folded && <div className="flex justify-center pb-3 border-b border-white/10">{foldButton}</div>}

        {!folded && (
          <div className="px-5 py-3 border-b border-white/10">
            <div className="font-mono text-[10px] tracking-[0.2em] text-slate-400 uppercase">organization</div>
            <div className="font-display font-semibold truncate text-white" data-testid="org-name">{org?.name || "—"}</div>
            <div className="font-mono text-[10px] tracking-[0.2em] text-slate-400 uppercase mt-2">plan · <span className="text-cyan-300">{org?.plan || "pro"}</span></div>
          </div>
        )}

        <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              title={folded ? item.label : undefined}
              aria-label={folded ? item.label : undefined}
              data-testid={`nav-${item.label.toLowerCase().replace(/\s/g, '-')}`}
              className={({ isActive }) =>
                `group relative flex items-center ${folded ? "justify-center px-0" : "gap-3 px-3"} py-2 rounded-xl transition-all ${
                  isActive
                    ? "bg-white/10 text-white shadow-[inset_0_0_0_1px_rgba(129,140,248,0.45),0_0_24px_-8px_rgba(99,102,241,0.8)]"
                    : "text-slate-300 hover:text-white hover:bg-white/5"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-gradient-to-b from-cyan-300 to-indigo-400" aria-hidden="true" />}
                  <item.icon size={19} weight="duotone" className={isActive ? "text-cyan-300" : ""} />
                  {!folded && <span className="font-display font-medium text-sm tracking-tight">{item.label}</span>}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className={`p-3 border-t border-white/10 ${folded ? "flex flex-col items-center gap-2" : ""}`}>
          <button
            onClick={() => setAiOpen(true)}
            className={`w-full inline-flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 via-violet-500 to-cyan-500 hover:shadow-[0_0_22px_-2px_rgba(99,102,241,0.9)] transition ${folded ? "px-0" : "px-3"}`}
            data-testid="open-ai-composer"
            title="AI composer"
            aria-label="AI composer"
          >
            <Sparkle size={15} weight="fill" /> {!folded && "AI COMPOSER"}
          </button>
          <button
            onClick={logout}
            className={`mt-2 w-full flex items-center ${folded ? "justify-center" : "gap-2 px-2"} py-2 text-sm text-slate-300 hover:text-cyan-300 transition-colors`}
            data-testid="logout-button"
            title={folded ? `Sign out (${user?.email || ""})` : undefined}
            aria-label={folded ? "Sign out" : undefined}
          >
            <SignOut size={16} /> {!folded && <span className="truncate">Sign out · <span className="font-mono">{user?.email}</span></span>}
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 md:min-h-0">
        <nav className="md:hidden flex items-center gap-1 overflow-x-auto px-3 py-2 bg-[#0B1020] text-slate-200 border-b border-indigo-400/20" aria-label="Main navigation (mobile)" data-testid="mobile-nav">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} aria-label={item.label} title={item.label}
              className={({ isActive }) => `flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs ${isActive ? "bg-white/10 text-white ring-1 ring-indigo-400/50" : "text-slate-300"}`}>
              <item.icon size={16} weight="duotone" /> {item.label}
            </NavLink>
          ))}
        </nav>
        <main className="flex-1 overflow-y-auto">
          <motion.div
            key={window.location.pathname}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            <Outlet />
          </motion.div>
        </main>
        <Footer />
      </div>

      <AIComposerModal open={aiOpen} onClose={() => setAiOpen(false)} />
    </div>
  );
}
