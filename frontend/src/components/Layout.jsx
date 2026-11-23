import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import {
  Briefcase,
  CaretLeft,
  CaretRight,
  Cpu,
  DotsThree,
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
  Stack,
  TrendUp,
  Users,
  X,
} from "@phosphor-icons/react";
const AIComposerModal = lazy(() => import("@/components/AIComposerModal"));
import Footer from "@/components/Footer";
import { LogoMark } from "@/components/Logo";
import { SECTIONS, activeNavItem, activeTab, sectionOf } from "@/lib/sections";
import { isTypingTarget, readPref, writePref } from "@/lib/uiPrefs";
import { prefetchAll, prefetchPath, whenIdle } from "@/lib/routes";

const ICONS = {
  SquaresFour,
  MapTrifold,
  Users,
  PaperPlaneTilt,
  TrendUp,
  Sparkle,
  Stack,
  Cpu,
  ShieldCheck,
  Briefcase,
  PlugsConnected,
  Gear,
  Heartbeat,
};

const FOCUS = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400";

// Offer approval belongs with the answers it produces: shown beside Outreach, never as another top-level destination.
const CONTEXT_DETAILS = {
  outreach: [{ to: "/app/settings/offer", label: "Offre & modèle", testId: "detail-offer" }],
};

// The sidebar holds exactly the six rubriques of the product. Their sub-sections stay in the section bar;
// NAV_GROUPS remains the route/title index used by activeNavItem and by the rest of the application.
function NavList({ folded, onNavigate, testPrefix = "" }) {
  const { pathname } = useLocation();
  const activeSection = sectionOf(pathname);

  return (
    <nav className="nav-list" aria-label="Rubriques Plantiers OutreachOS">
      <ul className="space-y-0.5">
        {SECTIONS.map((section) => {
          const Icon = ICONS[section.icon] || SquaresFour;
          const active = activeSection?.id === section.id;
          return (
            <li key={section.id}>
              <Link
                to={section.to}
                onClick={onNavigate}
                onMouseEnter={() => prefetchPath(section.to)}
                onFocus={() => prefetchPath(section.to)}
                title={section.label}
                aria-label={folded ? section.label : undefined}
                aria-current={active ? "page" : undefined}
                data-testid={`${testPrefix}${section.testId}`}
                className={`nav-rubrique ${folded ? "nav-rubrique-folded" : ""} ${FOCUS}`}
              >
                <Icon size={18} weight="duotone" className="nav-rubrique-icon" aria-hidden="true" />
                <span className="nav-rubrique-label">{section.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
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

  const [detailsOpen, setDetailsOpen] = useState(false);
  useEffect(() => setDetailsOpen(false), [pathname, search]);

  const current = section ? activeTab(section, pathname, search) : null;
  const currentNav = activeNavItem(pathname, search);
  const pageTitle = currentNav?.label || section?.label || "Plantiers OutreachOS";
  const primaryTabs = (section?.tabs || []).filter((tab) => !tab.secondary);
  const detailTabs = [
    ...(section?.tabs || []).filter((tab) => tab.secondary),
    ...(CONTEXT_DETAILS[section?.id] || []),
  ];

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

        {!isSuppressed && primaryTabs.length > 0 && (
          <nav
            className="flex min-w-0 items-center gap-1 ml-3 pl-3 border-l border-white/10"
            aria-label={`${section.label} : sous-sections`}
            data-testid="section-tabs"
          >
            {primaryTabs.map((tab) => {
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

      {!isSuppressed && detailTabs.length > 0 && (
        <div className="relative shrink-0">
          <button
            type="button"
            onClick={() => setDetailsOpen((open) => !open)}
            className={`section-details-toggle ${FOCUS}`}
            aria-expanded={detailsOpen}
            aria-haspopup="true"
            aria-label="Détails et écrans avancés"
            title="Détails et écrans avancés"
            data-testid="details-toggle"
          >
            <DotsThree size={16} weight="bold" />
            <span className="hidden lg:inline">Détails</span>
          </button>
          {detailsOpen && (
            <div
              className="details-panel"
              role="group"
              aria-label="Détails et écrans avancés"
              data-testid="details-panel"
            >
              <div className="mono-accent px-3 pb-1 pt-2">// détails</div>
              {detailTabs.map((link) => {
                const active = current && current.to === link.to;
                return (
                  <Link
                    key={link.to}
                    to={link.to}
                    onClick={() => setDetailsOpen(false)}
                    onMouseEnter={() => prefetchPath(link.to)}
                    onFocus={() => prefetchPath(link.to)}
                    aria-current={active ? "page" : undefined}
                    data-testid={link.testId}
                    className={`details-panel-link ${FOCUS}`}
                  >
                    {link.label}
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      )}

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
      className={`nav-header-action ${FOCUS}`}
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
        } nav-shell shrink-0 flex-col overflow-y-auto bg-sidebar text-white border-r border-white/10`}
        data-testid={mobile ? "mobile-drawer" : "sidebar"}
        data-folded={!mobile && folded}
        aria-label="Navigation Plantiers OutreachOS"
      >
        <div className="nav-brand-wrap">
          <div className={`nav-brand ${narrow ? "nav-brand-folded" : ""}`}>
            <LogoMark decorative className="h-8 shrink-0" />
            <div className="nav-wordmark" aria-hidden={narrow ? "true" : undefined}>
              <div className="text-sm font-extrabold tracking-tight text-white">PLANTIERS</div>
              <div className="mt-1 font-mono text-[9px] tracking-[0.25em] text-brand-lilac/80">OUTREACH OS</div>
            </div>
          </div>
          {mobile ? (
            <button
              ref={mobileCloseRef}
              type="button"
              onClick={() => setMobileOpen(false)}
              className={`nav-header-action ${FOCUS}`}
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
