import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import {
  SquaresFour, Target, Users, Robot, ChatsCircle, ChartLine, Gear, SignOut, Lightning, MagnifyingGlass, Sparkle,
} from "@phosphor-icons/react";
import { useState } from "react";
import AIComposerModal from "@/components/AIComposerModal";

const NAV = [
  { to: "/app/dashboard", icon: SquaresFour, label: "Dashboard" },
  { to: "/app/campaigns", icon: Target, label: "Campaigns" },
  { to: "/app/leads", icon: Users, label: "Leads CRM" },
  { to: "/app/agents", icon: Robot, label: "Agents" },
  { to: "/app/messages", icon: ChatsCircle, label: "Messages" },
  { to: "/app/analytics", icon: ChartLine, label: "Analytics" },
  { to: "/app/settings", icon: Gear, label: "Settings" },
];

export default function Layout() {
  const { user, org, logout } = useAuth();
  const navigate = useNavigate();
  const [aiOpen, setAiOpen] = useState(false);

  return (
    <div className="min-h-screen flex bg-[#050505] text-[#F8FAFC]">
      {/* Sidebar */}
      <aside className="hidden md:flex w-64 flex-col border-r border-[#262626] bg-[#080808] sticky top-0 h-screen">
        <div className="px-6 py-6 border-b border-[#262626]">
          <div className="flex items-center gap-2">
            <Lightning size={20} weight="fill" className="text-[#00E5FF]" />
            <div className="font-display font-black tracking-tight text-lg">OPENCLAW</div>
          </div>
          <div className="mono-accent text-[#4B5563] mt-1">/// command.center</div>
        </div>

        <div className="px-4 py-5 border-b border-[#262626]">
          <div className="mono-accent mb-1">organization</div>
          <div className="font-display font-semibold truncate" data-testid="org-name">{org?.name || "—"}</div>
          <div className="mono-accent text-[#8B949E] mt-2">plan · <span className="text-[#BF55EC]">{org?.plan || "pro"}</span></div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              data-testid={`nav-${item.label.toLowerCase().replace(/\s/g, '-')}`}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2.5 rounded-md transition-all ${
                  isActive
                    ? "bg-[#0f1416] text-[#00E5FF] border border-[#1f3a42]"
                    : "text-[#8B949E] hover:text-white hover:bg-[#101010] border border-transparent"
                }`
              }
            >
              <item.icon size={18} weight="duotone" />
              <span className="font-display font-medium text-sm tracking-tight">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-[#262626]">
          <button onClick={() => setAiOpen(true)} className="btn-purple w-full justify-center" data-testid="open-ai-composer">
            <Sparkle size={14} weight="fill" /> AI COMPOSER
          </button>
          <button onClick={logout} className="mt-3 w-full text-left flex items-center gap-2 text-sm text-[#8B949E] hover:text-white transition-colors px-2 py-2" data-testid="logout-button">
            <SignOut size={16} /> Sign out · <span className="font-mono truncate">{user?.email}</span>
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="sticky top-0 z-40 border-b border-[#262626] bg-[#050505]/80 backdrop-blur-xl">
          <div className="flex items-center justify-between px-6 py-4">
            <div className="flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-[#10B981] pulse-dot" />
              <span className="mono-accent">// all systems nominal</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 border border-[#262626] rounded-md bg-[#0A0A0A]">
                <MagnifyingGlass size={14} className="text-[#4B5563]" />
                <input placeholder="Search leads, campaigns…" className="bg-transparent outline-none text-sm w-56 font-mono" data-testid="global-search-input" />
                <span className="mono-accent text-[#4B5563]">⌘K</span>
              </div>
              <div className="flex items-center gap-2 px-3 py-1.5 border border-[#262626] rounded-md bg-[#0A0A0A]">
                <div className="w-6 h-6 rounded-full bg-gradient-to-br from-[#00E5FF] to-[#BF55EC] flex items-center justify-center text-xs font-bold text-black">
                  {(user?.full_name || "U").charAt(0).toUpperCase()}
                </div>
                <span className="text-sm font-medium hidden sm:inline" data-testid="user-name">{user?.full_name}</span>
              </div>
            </div>
          </div>
        </header>

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
      </div>

      <AIComposerModal open={aiOpen} onClose={() => setAiOpen(false)} />
    </div>
  );
}
