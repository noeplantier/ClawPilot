import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import {
  SquaresFour, Target, Users, Robot, ChatsCircle, ChartLine, Gear, SignOut, Lightning, MagnifyingGlass, Sparkle,
  ListChecks, PaperPlaneTilt,
} from "@phosphor-icons/react";
import { useState } from "react";
import AIComposerModal from "@/components/AIComposerModal";
import Footer from "@/components/Footer";

const NAV = [
  { to: "/app/dashboard", icon: SquaresFour, label: "Dashboard" },
  { to: "/app/campaigns", icon: Target, label: "Campaigns" },
  { to: "/app/leads", icon: Users, label: "Leads CRM" },
  { to: "/app/prospects", icon: MagnifyingGlass, label: "Prospects" },
  { to: "/app/prospects/review", icon: ListChecks, label: "Review queue" },
  { to: "/app/sending", icon: PaperPlaneTilt, label: "Sending" },
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
    <div className="min-h-screen flex bg-[#EDEBE0] text-[#0A0A0A] grid-bg">
      {/* Sidebar */}
      <aside className="hidden md:flex w-64 flex-col border-r-2 border-[#0F172A] bg-[#FFFFFF] sticky top-0 h-screen">
        <div className="px-6 py-6 border-b border-[#D6D3C8]">
          <div className="flex items-center gap-2">
            <Lightning size={20} weight="fill" className="text-[#DC2626]" />
            <div className="font-display font-black tracking-tight text-lg">OUTREACHOS</div>
          </div>
          <div className="mono-accent text-[#999995] mt-1">/// command.center</div>
        </div>

        <div className="px-4 py-5 border-b border-[#D6D3C8]">
          <div className="mono-accent mb-1">organization</div>
          <div className="font-display font-semibold truncate" data-testid="org-name">{org?.name || "—"}</div>
          <div className="mono-accent text-[#5F5F5A] mt-2">plan · <span className="text-[#0F172A]">{org?.plan || "pro"}</span></div>
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
                    ? "bg-[#FEF2F2] text-[#DC2626] border border-[#FCA5A5]"
                    : "text-[#595955] hover:text-[#0A0A0A] hover:bg-[#F4F2E7] border border-transparent"
                }`
              }
            >
              <item.icon size={18} weight="duotone" />
              <span className="font-display font-medium text-sm tracking-tight">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-[#D6D3C8]">
          <button onClick={() => setAiOpen(true)} className="btn-purple w-full justify-center" data-testid="open-ai-composer">
            <Sparkle size={14} weight="fill" /> AI COMPOSER
          </button>
          <button onClick={logout} className="mt-3 w-full text-left flex items-center gap-2 text-sm text-[#5F5F5A] hover:text-[#DC2626] transition-colors px-2 py-2" data-testid="logout-button">
            <SignOut size={16} /> Sign out · <span className="font-mono truncate">{user?.email}</span>
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
       

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
