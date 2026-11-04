import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { CaretLeft, CaretRight, Gear, List, MapTrifold, PaperPlaneTilt, SignOut, Sparkle, SquaresFour, Stack, Users, X } from "@phosphor-icons/react";
const AIComposerModal = lazy(() => import("@/components/AIComposerModal")); // only fetched when the composer is opened
import Footer from "@/components/Footer";
import { LogoMark } from "@/components/Logo";
import { SECTIONS, activeTab, sectionOf } from "@/lib/sections";
import { isTypingTarget, readPref, writePref } from "@/lib/uiPrefs";
import { prefetchAll, prefetchPath, whenIdle } from "@/lib/routes";

const ICONS = { SquaresFour, MapTrifold, Users, Stack, PaperPlaneTilt, Gear };
const FOCUS = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400";

// Exactly six entries, flat. What lives inside a section is the row of tabs above the content (SectionTabs), not a tree here.
function NavList({ folded, onNavigate, testPrefix = "" }) {
  const current = sectionOf(useLocation().pathname);
  return (
    <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-3" aria-label="Navigation principale">
      <ul className="space-y-1">
        {SECTIONS.map((section) => {
          const Icon = ICONS[section.icon];
          const active = current && current.id === section.id;
          return (
            <li key={section.id}>
              <Link
                to={section.to}
                onClick={onNavigate}
                onMouseEnter={() => prefetchPath(section.to)}
                onFocus={() => prefetchPath(section.to)}
                title={folded ? section.label : undefined}
                aria-label={folded ? section.label : undefined}
                aria-current={active ? "page" : undefined}
                data-testid={`${testPrefix}nav-${section.id}`}
                className={`relative flex min-h-11 items-center ${folded ? "justify-center" : "gap-3 px-3"} rounded-xl text-sm transition-colors [@media(max-height:620px)]:min-h-9 ${FOCUS} ${active ? "bg-brand-violet/20 text-white" : "text-sidebar-muted hover:bg-white/[0.06] hover:text-white"}`}
              >
                {active && <span aria-hidden="true" className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-brand-400" />}
                <Icon size={19} weight="duotone" />
                {!folded && <span className="font-medium">{section.label}</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

// Navigation inside the current section, above its content. Scrolls sideways on a narrow screen: nothing is hidden.
function SectionTabs({ onCompose }) {
  const { pathname, search } = useLocation();
  const section = sectionOf(pathname);
  if (!section) return null;
  const current = activeTab(section, pathname, search);
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-white/10 bg-void-elevated/80 px-3 md:px-6" data-testid="section-bar">
      <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto py-2" aria-label={`${section.label} : sections`} data-testid="section-tabs">
        <span className="mr-2 hidden shrink-0 font-mono text-[11px] uppercase tracking-[0.18em] text-brand-lilac sm:inline" data-testid="section-title">{section.label}</span>
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
              className={`relative shrink-0 rounded-lg px-3 py-1.5 text-sm transition-colors ${FOCUS} ${active ? "text-white" : "text-white/70 hover:bg-white/[0.06] hover:text-white"}`}
            >
              {tab.label}
              {active && <span aria-hidden="true" className="absolute inset-x-2 -bottom-0.5 h-px bg-gradient-to-r from-transparent via-brand-300 to-transparent" />}
            </Link>
          );
        })}
      </nav>
      <button type="button" onClick={onCompose} className={`inline-flex min-h-9 shrink-0 items-center gap-2 rounded-lg border border-white/[0.1] bg-white/[0.04] px-3 text-sm text-white/90 transition-colors hover:border-white/20 hover:bg-white/[0.08] ${FOCUS}`} data-testid="open-ai-composer" title="Composer IA" aria-label="Composer IA">
        <Sparkle size={16} weight="fill" className="text-brand-lilac" /> <span className="hidden sm:inline">Composer IA</span>
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
  useEffect(() => { whenIdle(prefetchAll); }, []); // every screen is warm before it is asked for
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

  // "[" folds or unfolds the sidebar, never while typing in a field.
  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "[" && !isTypingTarget(event.target) && !event.ctrlKey && !event.metaKey && !event.altKey) setFolded((value) => !value);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const foldButton = (
    <button onClick={() => setFolded((value) => !value)} className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-brand-lilac transition hover:bg-white/[0.08] ${FOCUS}`}
      aria-label={folded ? "Déplier la navigation" : "Replier la navigation"} aria-expanded={!folded} title={folded ? "Déplier la navigation ([)" : "Replier la navigation ([)"} data-testid="sidebar-toggle">
      {folded ? <CaretRight size={15} weight="bold" /> : <CaretLeft size={15} weight="bold" />}
    </button>
  );

  const sidebar = (mobile = false) => {
    const narrow = folded && !mobile;
    return (
      <aside className={`${mobile ? "flex fixed inset-y-0 left-0 z-[1001] w-[min(20rem,86vw)] shadow-2xl" : `hidden md:flex ${folded ? "w-[4.5rem]" : "w-64"} sticky top-0 h-screen`} shrink-0 flex-col overflow-y-auto bg-sidebar text-white border-r border-white/10 transition-[width] duration-200`}
        data-testid={mobile ? "mobile-drawer" : "sidebar"} data-folded={!mobile && folded} aria-label="Navigation Plantiers OutreachOS">
        <div className={`flex min-h-[4.5rem] items-center gap-3 border-b border-white/10 [@media(max-height:620px)]:min-h-[3.5rem] ${narrow ? "justify-center px-2" : "px-4"}`}>
          <LogoMark decorative className="h-9" />
          {!narrow && <div className="min-w-0 flex-1 leading-none"><div className="text-base font-extrabold tracking-tight text-white">PLANTIERS</div><div className="mt-1 font-mono text-[9px] tracking-[0.25em] text-brand-lilac/80">OUTREACHOS</div></div>}
          {mobile ? <button ref={mobileCloseRef} type="button" onClick={() => setMobileOpen(false)} className={`flex h-9 w-9 items-center justify-center rounded-lg text-sidebar-muted hover:bg-white/10 hover:text-white ${FOCUS}`} aria-label="Fermer la navigation"><X size={18} /></button> : foldButton}
        </div>
        <NavList folded={narrow} onNavigate={() => setMobileOpen(false)} testPrefix={mobile ? "mobile-" : ""} />
        <div className={`border-t border-white/10 p-3 ${narrow ? "flex flex-col items-center" : ""}`} data-testid="account">
          {!narrow && (
            <div className="px-2 pb-2 [@media(max-height:620px)]:hidden">
              <div className="truncate text-sm font-medium text-white" data-testid="org-name">{org?.name || "—"}</div>
              <div className="truncate font-mono text-[11px] text-sidebar-muted" data-testid="user-email">{user?.email}</div>
            </div>
          )}
          <button onClick={logout} className={`flex min-h-9 w-full items-center ${narrow ? "justify-center" : "gap-2 px-2"} rounded-lg text-sm text-sidebar-muted transition-colors hover:bg-white/[0.06] hover:text-white ${FOCUS}`} data-testid="logout-button" title={narrow ? `Déconnexion (${user?.email || ""})` : undefined} aria-label={narrow ? "Déconnexion" : undefined}>
            <SignOut size={16} /> {!narrow && <span>Déconnexion</span>}
          </button>
        </div>
      </aside>
    );
  };

  return (
    <div className="min-h-screen md:h-screen flex bg-sidebar text-foreground">
      {sidebar()}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-white/10 bg-sidebar px-3 text-white md:hidden">
          <div className="flex items-center gap-2"><LogoMark decorative className="h-7" /><span className="text-sm font-extrabold tracking-tight">PLANTIERS</span></div>
          <button ref={mobileToggleRef} type="button" onClick={() => setMobileOpen(true)} className={`flex h-9 items-center gap-2 rounded-lg px-3 text-sm text-sidebar-muted hover:bg-white/10 hover:text-white ${FOCUS}`} aria-haspopup="dialog" aria-expanded={mobileOpen} aria-label="Ouvrir la navigation" data-testid="mobile-nav-toggle"><List size={18} /> Menu</button>
        </header>
        <SectionTabs onCompose={() => setAiOpen(true)} />
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
