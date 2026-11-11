import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import {
  Briefcase,
  CaretDown,
  CaretLeft,
  CaretRight,
  CaretUp,
  Cpu,
  Gear,
  Heartbeat,
  List,
  MapTrifold,
  PaperPlaneTilt,
  PlugsConnected,
  ShieldCheck,
  SignOut,
  Sparkle,
  SquaresFour,
  TrendUp,
  Users,
  X,
} from "@phosphor-icons/react";
const AIComposerModal = lazy(() => import("@/components/AIComposerModal"));
import Footer from "@/components/Footer";
import { LogoMark } from "@/components/Logo";
import { NAV_GROUPS, activeNavItem, activeTab, sectionOf } from "@/lib/sections";
import { isTypingTarget, readPref, writePref } from "@/lib/uiPrefs";
import { prefetchAll, prefetchPath, whenIdle } from "@/lib/routes";

const ICONS = {
  SquaresFour,
  MapTrifold,
  Users,
  PaperPlaneTilt,
  TrendUp,
  Sparkle,
  Cpu,
  ShieldCheck,
  Briefcase,
  PlugsConnected,
  Gear,
  Heartbeat,
};

const FOCUS = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400";

function NavList({ folded, onNavigate, testPrefix = "" }) {
  const { pathname, search } = useLocation();
  const currentItem = activeNavItem(pathname, search);
  const [collapsedGroups, setCollapsedGroups] = useState(() => {
    return readPref("sidebar.collapsedGroups", {});
  });

  const toggleGroup = (groupId) => {
    setCollapsedGroups((prev) => {
      const next = { ...prev, [groupId]: !prev[groupId] };
      writePref("sidebar.collapsedGroups", next);
      return next;
    });
  };

  return (
    <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-3 space-y-4" aria-label="Navigation principale">
      {NAV_GROUPS.map((group) => {
        const isCollapsed = !folded && !!collapsedGroups[group.id];
        return (
          <div key={group.id} className="space-y-1">
            {!folded && (
              <div className="flex items-center justify-between px-3 py-1">
                <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-brand-lilac/70">
                  // {group.label}
                </span>
                <button
                  type="button"
                  onClick={() => toggleGroup(group.id)}
                  className="text-white/40 hover:text-white transition p-0.5"
                  aria-label={isCollapsed ? `Déplier ${group.label}` : `Replier ${group.label}`}
                >
                  {isCollapsed ? <CaretDown size={11} /> : <CaretUp size={11} />}
                </button>
              </div>
            )}
            {!isCollapsed && (
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = ICONS[item.icon] || SquaresFour;
                  const active = currentItem && currentItem.id === item.id;
                  return (
                    <li key={item.id}>
                      <Link
                        to={item.to}
                        onClick={onNavigate}
                        onMouseEnter={() => prefetchPath(item.to)}
                        onFocus={() => prefetchPath(item.to)}
                        title={folded ? item.label : undefined}
                        aria-label={folded ? item.label : undefined}
                        aria-current={active ? "page" : undefined}
                        data-testid={`${testPrefix}${item.testId}`}
                        className={`relative flex min-h-10 items-center ${
                          folded ? "justify-center px-1" : "gap-3 px-3"
                        } rounded-xl text-sm transition-all duration-150 ${FOCUS} ${
                          active
                            ? "bg-brand-violet/20 text-white font-medium shadow-[inset_0_1px_0_rgba(255,255,255,0.1)]"
                            : "text-sidebar-muted hover:bg-white/[0.06] hover:text-white"
                        }`}
                      >
                        {active && (
                          <span
                            aria-hidden="true"
                            className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-brand-400 shadow-[0_0_8px_rgba(155,116,250,0.8)]"
                          />
                        )}
                        <Icon size={18} weight="duotone" className={active ? "text-brand-300" : ""} />
                        {!folded && (
                          <div className="flex flex-1 items-center justify-between min-w-0">
                            <span className="truncate">{item.label}</span>
                            {item.liveDot && (
                              <span
                                className="inline-block h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(74,222,128,0.8)] animate-pulse ml-2"
                                title="Live map"
                              />
                            )}
                            {item.statusDot && (
                              <span
                                className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_4px_rgba(74,222,128,0.6)] ml-2"
                                title="Operational"
                              />
                            )}
                          </div>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </nav>
  );
}

// Navigation inside current section: suppressed entirely for configuration destinations (Offer, Settings, Automations, System Health)
// which now live directly in the left sidebar as requested!
function SectionTabs({ onCompose }) {
  const { pathname, search } = useLocation();
  const section = sectionOf(pathname);

  // Per mandate: completely remove upper navigation elements for Offer, Settings, Automations, System Health
  const isSuppressed = !section || section.id === "control";

  const current = section ? activeTab(section, pathname, search) : null;
  const currentNav = activeNavItem(pathname, search);
  const pageTitle = currentNav?.label || section?.label || "Plantiers OutreachOS";

  return (
    <div
      className="flex shrink-0 items-center justify-between gap-2 border-b border-white/10 bg-void-elevated/80 px-3 md:px-6"
      data-testid="section-bar"
    >
      <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto py-2">
        <span
          className="shrink-0 font-mono text-[11px] uppercase tracking-[0.18em] text-brand-lilac"
          data-testid="section-title"
        >
          {pageTitle}
        </span>

        {!isSuppressed && section?.tabs?.length > 1 && (
          <nav
            className="flex min-w-0 items-center gap-1 ml-3 pl-3 border-l border-white/10"
            aria-label={`${section.label} : sous-sections`}
            data-testid="section-tabs"
          >
            {section.tabs.map((tab) => {
              const active = current && current.to === tab.to;
              return (
                <Link
                  key={tab.to}
                  to={tab.to}
                  onMouseEnter={() => prefetchPath(tab.to)}
                  onFocus={() => prefetchPath(tab.to)}
                  aria-current={active ? "page" : undefined}
                  data-testid={tab.testId}
                  className={`relative shrink-0 rounded-lg px-2.5 py-1 text-xs transition-colors ${FOCUS} ${
                    active ? "text-white font-medium bg-white/[0.08]" : "text-white/70 hover:bg-white/[0.04] hover:text-white"
                  }`}
                >
                  {tab.label}
                  {active && (
                    <span
                      aria-hidden="true"
                      className="absolute inset-x-2 -bottom-1 h-[2px] bg-gradient-to-r from-transparent via-brand-300 to-transparent"
                    />
                  )}
                </Link>
              );
            })}
          </nav>
        )}
      </div>

      <button
        type="button"
        onClick={onCompose}
        className={`inline-flex min-h-8 shrink-0 items-center gap-2 rounded-lg border border-white/[0.1] bg-white/[0.04] px-3 text-xs text-white/90 transition-colors hover:border-white/20 hover:bg-white/[0.08] ${FOCUS}`}
        data-testid="open-ai-composer"
        title="Composer IA"
        aria-label="Composer IA"
      >
        <Sparkle size={14} weight="fill" className="text-brand-lilac" />{" "}
        <span className="hidden sm:inline">Composer IA</span>
      </button>
    </div>
  );
}

export default function Layout() {
  const { user, org, logout } = useAuth();
  const [aiOpen, setAiOpen] = useState(false);
  const [folded, setFolded] = useState(() => readPref("sidebar.folded", false));
  const [mobileOpen, setMobileOpen] = useState(false);
  const mobileToggleRef = useRef(null);
  const mobileCloseRef = useRef(null);
  const mobileDialogRef = useRef(null);
  const restoreMobileFocusRef = useRef(false);

  useEffect(() => writePref("sidebar.folded", folded), [folded]);
  useEffect(() => {
    whenIdle(prefetchAll);
  }, []);

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
      if (event.key === "Escape") {
        setMobileOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = mobileDialogRef.current?.querySelectorAll("a[href], button:not([disabled])");
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  // "[" folds or unfolds the sidebar, never while typing in a field.
  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "[" && !isTypingTarget(event.target) && !event.ctrlKey && !event.metaKey && !event.altKey) {
        setFolded((value) => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const foldButton = (
    <button
      onClick={() => setFolded((value) => !value)}
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-brand-lilac transition hover:bg-white/[0.08] ${FOCUS}`}
      aria-label={folded ? "Déplier la navigation" : "Replier la navigation"}
      aria-expanded={!folded}
      title={folded ? "Déplier la navigation ([)" : "Replier la navigation ([)"}
      data-testid="sidebar-toggle"
    >
      {folded ? <CaretRight size={15} weight="bold" /> : <CaretLeft size={15} weight="bold" />}
    </button>
  );

  const sidebar = (mobile = false) => {
    const narrow = folded && !mobile;
    return (
      <aside
        className={`${
          mobile
            ? "flex fixed inset-y-0 left-0 z-[1001] w-[min(20rem,86vw)] shadow-2xl"
            : `hidden md:flex ${folded ? "w-[4.5rem]" : "w-64"} sticky top-0 h-screen`
        } shrink-0 flex-col overflow-y-auto bg-sidebar text-white border-r border-white/10 transition-[width] duration-200`}
        data-testid={mobile ? "mobile-drawer" : "sidebar"}
        data-folded={!mobile && folded}
        aria-label="Navigation Plantiers OutreachOS"
      >
        <div
          className={`flex min-h-[4.25rem] items-center gap-3 border-b border-white/10 [@media(max-height:620px)]:min-h-[3.5rem] ${
            narrow ? "justify-center px-2" : "px-4"
          }`}
        >
          <LogoMark decorative className="h-8" />
          {!narrow && (
            <div className="min-w-0 flex-1 leading-none">
              <div className="text-sm font-extrabold tracking-tight text-white">PLANTIERS</div>
              <div className="mt-1 font-mono text-[9px] tracking-[0.25em] text-brand-lilac/80">OUTREACH OS</div>
            </div>
          )}
          {mobile ? (
            <button
              ref={mobileCloseRef}
              type="button"
              onClick={() => setMobileOpen(false)}
              className={`flex h-8 w-8 items-center justify-center rounded-lg text-sidebar-muted hover:bg-white/10 hover:text-white ${FOCUS}`}
              aria-label="Fermer la navigation"
            >
              <X size={18} />
            </button>
          ) : (
            foldButton
          )}
        </div>
        <NavList folded={narrow} onNavigate={() => setMobileOpen(false)} testPrefix={mobile ? "mobile-" : ""} />
        <div className={`border-t border-white/10 p-3 ${narrow ? "flex flex-col items-center" : ""}`} data-testid="account">
          {!narrow && (
            <div className="px-2 pb-2 [@media(max-height:620px)]:hidden">
              <div className="truncate text-sm font-medium text-white" data-testid="org-name">
                {org?.name || "—"}
              </div>
              <div className="truncate font-mono text-[11px] text-sidebar-muted" data-testid="user-email">
                {user?.email}
              </div>
            </div>
          )}
          <button
            onClick={logout}
            className={`flex min-h-8 w-full items-center ${
              narrow ? "justify-center" : "gap-2 px-2"
            } rounded-lg text-xs text-sidebar-muted transition-colors hover:bg-white/[0.06] hover:text-white ${FOCUS}`}
            data-testid="logout-button"
            title={narrow ? `Déconnexion (${user?.email || ""})` : undefined}
            aria-label={narrow ? "Déconnexion" : undefined}
          >
            <SignOut size={15} /> {!narrow && <span>Déconnexion</span>}
          </button>
        </div>
      </aside>
    );
  };

  return (
    <div className="h-screen flex bg-sidebar text-foreground overflow-hidden">
      {sidebar()}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col h-screen overflow-hidden">
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-white/10 bg-sidebar px-3 text-white md:hidden">
          <div className="flex items-center gap-2">
            <LogoMark decorative className="h-7" />
            <span className="text-sm font-extrabold tracking-tight">PLANTIERS</span>
          </div>
          <button
            ref={mobileToggleRef}
            type="button"
            onClick={() => setMobileOpen(true)}
            className={`flex h-9 items-center gap-2 rounded-lg px-3 text-sm text-sidebar-muted hover:bg-white/10 hover:text-white ${FOCUS}`}
            aria-haspopup="dialog"
            aria-expanded={mobileOpen}
            aria-label="Ouvrir la navigation"
            data-testid="mobile-nav-toggle"
          >
            <List size={18} /> Menu
          </button>
        </header>
        <SectionTabs onCompose={() => setAiOpen(true)} />
        <main className="grid-bg min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
        <Footer className="hidden" />
      </div>
      {mobileOpen && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-[1000] bg-black/60 md:hidden backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-label="Fermer le menu"
          />
          <div
            ref={mobileDialogRef}
            role="dialog"
            aria-modal="true"
            aria-label="Navigation mobile"
            className="fixed inset-0 z-[1001] md:hidden"
          >
            {sidebar(true)}
          </div>
        </>
      )}
      {aiOpen && (
        <Suspense fallback={null}>
          <AIComposerModal open={aiOpen} onClose={() => setAiOpen(false)} />
        </Suspense>
      )}
    </div>
  );
}
