import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import {
  SquaresFour, Target, Users, Robot, ChatsCircle, ChartLine, Gear, SignOut, MagnifyingGlass, Sparkle,
  ListChecks, PaperPlaneTilt, MapTrifold, Database, Heartbeat, CaretLeft, CaretRight, CaretDown, List, X,
} from "@phosphor-icons/react";
const AIComposerModal = lazy(() => import("@/components/AIComposerModal")); // only fetched when the composer is opened
import Footer from "@/components/Footer";
import { LogoMark } from "@/components/Logo";
import { isTypingTarget, readPref, writePref } from "@/lib/uiPrefs";
import { prefetchAll, prefetchPath, whenIdle } from "@/lib/routes";

const GROUPS = [
  { id: "overview", label: "Vue d’ensemble", icon: SquaresFour, items: [
    { to: "/app/dashboard", label: "Vue d’ensemble", icon: SquaresFour, testId: "nav-dashboard" },
  ] },
  { id: "prospecting", label: "Prospection", icon: MapTrifold, items: [
    { to: "/app/map", label: "Carte", icon: MapTrifold, testId: "nav-map-search" },
    { to: "/app/sources", label: "Sources", icon: Database, testId: "nav-sources" },
    { to: "/app/prospects", label: "Prospects", icon: MagnifyingGlass, testId: "nav-prospects" },
    { to: "/app/prospects/review", label: "À vérifier", icon: ListChecks, testId: "nav-review-queue" },
  ] },
  { id: "crm", label: "CRM", icon: Users, items: [
    { to: "/app/leads", label: "Contacts et entreprises", icon: Users, testId: "nav-leads-crm" },
    { to: "/app/leads?view=kanban", label: "Pipeline", icon: ListChecks, testId: "nav-pipeline" },
  ] },
  { id: "outreach", label: "Outreach", icon: PaperPlaneTilt, items: [
    { to: "/app/campaigns", label: "Campagnes", icon: Target, testId: "nav-campaigns" },
    { to: "/app/messages", label: "Boîte de réception", icon: ChatsCircle, testId: "nav-messages" },
    { to: "/app/sending", label: "Canaux", icon: PaperPlaneTilt, testId: "nav-sending" },
  ] },
  { id: "control", label: "Pilotage", icon: Gear, items: [
    { to: "/app/agents", label: "Automatisations", icon: Robot, testId: "nav-agents" },
    { to: "/app/analytics", label: "Analytics", icon: ChartLine, testId: "nav-analytics" },
    { to: "/app/system", label: "System health", icon: Heartbeat, testId: "nav-system-health" },
    { to: "/app/settings", label: "Intégrations et réglages", icon: Gear, testId: "nav-settings" },
  ] },
];

function groupForPath(pathname) {
  return GROUPS.find((group) => group.items.some((item) => {
    const itemPath = item.to.split("?")[0];
    return pathname === itemPath || pathname.startsWith(`${itemPath}/`);
  }))?.id || "overview";
}

function NavGroups({ folded, openGroup, setOpenGroup, setFolded, onNavigate, testPrefix = "" }) {
  const location = useLocation();
  return (
    <nav className="flex-1 min-h-0 px-3 py-3" aria-label="Navigation principale">
      <div className="space-y-1">
        {GROUPS.map((group) => {
          const expanded = openGroup === group.id;
          const active = groupForPath(location.pathname) === group.id;
          const GroupIcon = group.icon;
          return (
            <section key={group.id} aria-label={group.label}>
              {group.items.length === 1 ? (
                <NavLink
                  to={group.items[0].to}
                  end
                  onClick={onNavigate}
                  onMouseEnter={() => prefetchPath(group.items[0].to)}
                  onFocus={() => prefetchPath(group.items[0].to)}
                  title={folded ? group.label : undefined}
                  aria-label={folded ? group.label : undefined}
                  data-testid={`${testPrefix}${group.items[0].testId}`}
                  className={({ isActive }) => `group relative flex min-h-10 items-center ${folded ? "justify-center px-0" : "gap-3 px-3"} rounded-lg px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-lilac ${isActive ? "bg-brand-violet/20 text-white" : "text-sidebar-muted hover:bg-white/[0.06] hover:text-white"}`}
                >
                  <GroupIcon size={19} weight="duotone" />{!folded && <span className="font-medium">{group.label}</span>}
                </NavLink>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => { if (folded) { setFolded(false); setOpenGroup(group.id); } else setOpenGroup(expanded ? null : group.id); }}
                    title={folded ? group.label : undefined}
                    aria-label={folded ? group.label : undefined}
                    aria-expanded={expanded}
                    aria-controls={`nav-group-${group.id}`}
                    data-testid={`${testPrefix}nav-group-${group.id}`}
                    className={`group relative flex min-h-10 w-full items-center ${folded ? "justify-center px-0" : "gap-3 px-3"} rounded-lg text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-lilac ${active ? "text-white" : "text-sidebar-muted hover:bg-white/[0.06] hover:text-white"} ${expanded && !folded ? "bg-white/[0.05]" : ""}`}
                  >
                    <GroupIcon size={19} weight="duotone" />
                    {!folded && <><span className="min-w-0 flex-1">{group.label}</span><CaretDown size={14} className={`transition-transform ${expanded ? "rotate-180" : ""}`} /></>}
                  </button>
                  {expanded && !folded && (
                    <div id={`nav-group-${group.id}`} className="ml-[1.15rem] mt-1 space-y-0.5 border-l border-white/10 pl-2">
                      {group.items.map((item) => {
                        const ItemIcon = item.icon;
                        const [itemPath, itemQuery] = item.to.split("?");
                        const active = location.pathname === itemPath && (itemQuery ? location.search === `?${itemQuery}` : location.search !== "?view=kanban");
                        return <Link key={item.testId} to={item.to} onClick={onNavigate} onMouseEnter={() => prefetchPath(item.to)} onFocus={() => prefetchPath(item.to)} data-testid={`${testPrefix}${item.testId}`} aria-current={active ? "page" : undefined}
                          className={`flex min-h-9 items-center gap-2 rounded-md px-2 text-[13px] leading-4 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-lilac ${active ? "bg-brand-violet/20 text-white" : "text-sidebar-muted hover:bg-white/[0.06] hover:text-white"}`}>
                          <ItemIcon size={16} weight="duotone" /><span>{item.label}</span>
                        </Link>;
                      })}
                    </div>
                  )}
                </>
              )}
            </section>
          );
        })}
      </div>
    </nav>
  );
}

export default function Layout() {
  const { user, org, logout } = useAuth();
  const location = useLocation();
  const [aiOpen, setAiOpen] = useState(false);
  const [folded, setFolded] = useState(() => readPref("sidebar.folded", false));
  const [openGroup, setOpenGroup] = useState(() => groupForPath(window.location.pathname));
  const [mobileOpen, setMobileOpen] = useState(false);
  const mobileToggleRef = useRef(null);
  const mobileCloseRef = useRef(null);
  const mobileDialogRef = useRef(null);
  const restoreMobileFocusRef = useRef(false);

  useEffect(() => writePref("sidebar.folded", folded), [folded]);
  useEffect(() => { whenIdle(prefetchAll); }, []); // every screen is warm before it is asked for
  useEffect(() => setOpenGroup(groupForPath(location.pathname)), [location.pathname]);
  useEffect(() => {
    if (!mobileOpen) {
      if (restoreMobileFocusRef.current) {
        restoreMobileFocusRef.current = false;
        mobileToggleRef.current.focus();
      }
      return undefined;
    }
    restoreMobileFocusRef.current = true;
    mobileCloseRef.current?.focus();
    const onKey = (event) => {
      if (event.key === "Escape") { setMobileOpen(false); return; }
      if (event.key !== "Tab") return;
      const focusable = mobileDialogRef.current?.querySelectorAll("a[href], button:not([disabled])");
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  // Keep the sidebar shortcut available and ignore focused text fields.
  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "[" && !isTypingTarget(event.target) && !event.ctrlKey && !event.metaKey && !event.altKey) setFolded((value) => !value);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const foldButton = (
    <button onClick={() => setFolded((value) => !value)} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-brand-lilac hover:bg-white/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-lilac transition"
      aria-label={folded ? "Déplier la navigation" : "Replier la navigation"} aria-expanded={!folded} title={folded ? "Déplier la navigation ([)" : "Replier la navigation ([)"} data-testid="sidebar-toggle">
      {folded ? <CaretRight size={15} weight="bold" /> : <CaretLeft size={15} weight="bold" />}
    </button>
  );

  const sidebar = (mobile = false) => (
    <aside className={`${mobile ? "flex fixed inset-y-0 left-0 z-[1001] w-[min(20rem,86vw)] shadow-2xl" : `hidden md:flex ${folded ? "w-[4.5rem]" : "w-64"} sticky top-0 h-screen`} shrink-0 flex-col overflow-y-auto bg-sidebar text-white border-r border-white/10 transition-[width] duration-200`}
      data-testid={mobile ? "mobile-drawer" : "sidebar"} data-folded={!mobile && folded} aria-label="Navigation Plantiers OutreachOS">
      <div className={`flex min-h-[4.5rem] items-center gap-3 border-b border-white/10 ${folded && !mobile ? "justify-center px-2" : "px-4"}`}>
        <LogoMark decorative className="h-9" />
        {(!folded || mobile) && <div className="min-w-0 flex-1 leading-none"><div className="text-base font-extrabold tracking-tight text-white">PLANTIERS</div><div className="mt-1 font-mono text-[9px] tracking-[0.25em] text-brand-lilac/80">OUTREACHOS</div></div>}
        {mobile ? <button ref={mobileCloseRef} type="button" onClick={() => setMobileOpen(false)} className="flex h-9 w-9 items-center justify-center rounded-lg text-sidebar-muted hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-lilac" aria-label="Fermer la navigation"><X size={18} /></button> : foldButton}
      </div>
      {(!folded || mobile) && <div className="border-b border-white/10 px-5 py-3"><div className="text-[10px] font-medium uppercase tracking-[0.14em] text-sidebar-muted">Espace de travail</div><div className="mt-1 truncate text-sm font-medium text-white" data-testid="org-name">{org?.name || "—"}</div></div>}
      <NavGroups folded={folded && !mobile} openGroup={openGroup} setOpenGroup={setOpenGroup} setFolded={setFolded} onNavigate={() => setMobileOpen(false)} testPrefix={mobile ? "mobile-" : ""} />
      <div className={`border-t border-white/10 p-3 ${folded && !mobile ? "flex flex-col items-center gap-2" : ""}`}>
        <button onClick={() => { setAiOpen(true); setMobileOpen(false); }} className={`inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-lg bg-brand-violet px-3 text-sm font-semibold text-white transition hover:bg-brand-violet-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-lilac ${folded && !mobile ? "px-0" : ""}`} data-testid="open-ai-composer" title="AI composer" aria-label="AI composer">
          <Sparkle size={16} weight="fill" /> {(!folded || mobile) && "Composer IA"}
        </button>
        <button onClick={logout} className={`mt-2 flex min-h-9 w-full items-center ${folded && !mobile ? "justify-center" : "gap-2 px-2"} rounded-md text-sm text-sidebar-muted transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-lilac`} data-testid="logout-button" title={folded && !mobile ? `Déconnexion (${user?.email || ""})` : undefined} aria-label={folded && !mobile ? "Déconnexion" : undefined}>
          <SignOut size={16} /> {(!folded || mobile) && <span className="truncate">Déconnexion · <span className="font-mono">{user?.email}</span></span>}
        </button>
      </div>
    </aside>
  );

  return (
    <div className="min-h-screen md:h-screen flex bg-sidebar text-foreground">
      {sidebar()}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-white/10 bg-sidebar px-3 text-white md:hidden">
          <div className="flex items-center gap-2"><LogoMark decorative className="h-7" /><span className="text-sm font-extrabold tracking-tight">PLANTIERS</span></div>
          <button ref={mobileToggleRef} type="button" onClick={() => setMobileOpen(true)} className="flex h-9 items-center gap-2 rounded-lg px-3 text-sm text-sidebar-muted hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-lilac" aria-haspopup="dialog" aria-expanded={mobileOpen} aria-label="Ouvrir la navigation" data-testid="mobile-nav-toggle"><List size={18} /> Menu</button>
        </header>
        <main className="grid-bg min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
        <Footer />
      </div>
      {mobileOpen && <><button type="button" className="fixed inset-0 z-[1000] bg-black/60 md:hidden" onClick={() => setMobileOpen(false)} aria-label="Fermer le menu" /><div ref={mobileDialogRef} role="dialog" aria-modal="true" aria-label="Navigation mobile" className="fixed inset-0 z-[1001] md:hidden">{sidebar(true)}</div></>}
      {aiOpen && <Suspense fallback={null}><AIComposerModal open={aiOpen} onClose={() => setAiOpen(false)} /></Suspense>}
    </div>
  );
}
