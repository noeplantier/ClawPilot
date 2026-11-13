import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { List } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import Footer from "@/components/Footer";
import Logo from "@/components/Logo";
import { usageApi, useAsync } from "@/lib/outreach";
import { tightest } from "@/lib/creditsFormat";
import Sidebar, { FOCUS } from "@/components/shell/Sidebar";
import { isTypingTarget, readPref, writePref } from "@/lib/uiPrefs";
import { prefetchAll, whenIdle } from "@/lib/routes";
const AIComposerModal = lazy(() => import("@/components/AIComposerModal")); // only fetched when the composer is opened
const CommandPalette = lazy(() => import("@/components/CommandPalette")); // idem: cmdk is not part of the first load
const UsageDialog = lazy(() => import("@/components/usage/UsageDialog")); // credits and outreach models, on demand

// The application frame. No global top bar: the six entries and their screens are in the sidebar, the tools (go-to palette,
// AI composer) at its foot, and each page owns its title. This component only holds the state and the keyboard.
export default function Layout() {
  const { user, org, logout } = useAuth();
  const navigate = useNavigate();
  const [aiOpen, setAiOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [usageOpen, setUsageOpen] = useState(false);
  // The credits left (session of 5 h, day), refreshed every minute: the sidebar shows the tightest one.
  const usage = useAsync(() => usageApi.credits(), [usageOpen], { key: "usage:credits", intervalMs: 60000 });
  const meterOf = usage.data ? tightest(usage.data.windows) : null;
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
        mobileToggleRef.current?.focus();
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

  // "[" folds or unfolds the sidebar, never while typing; Ctrl or Cmd + K opens the go-to palette, even while typing.
  useEffect(() => {
    const onKey = (event) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") { event.preventDefault(); setPaletteOpen((value) => !value); return; }
      if (event.key === "[" && !isTypingTarget(event.target) && !event.ctrlKey && !event.metaKey && !event.altKey) setFolded((value) => !value);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggleFold = useCallback(() => setFolded((value) => !value), []);
  const run = useCallback((command) => {
    if (command.to) navigate(command.to);
    else if (command.action === "compose") setAiOpen(true);
    else if (command.action === "fold") toggleFold();
    else if (command.action === "logout") logout();
    else if (command.action === "usage") setUsageOpen(true);
  }, [navigate, toggleFold, logout]);
  const common = { user, org, onCompose: () => { setMobileOpen(false); setAiOpen(true); }, onPalette: () => { setMobileOpen(false); setPaletteOpen(true); }, onLogout: logout,
    onUsage: () => { setMobileOpen(false); setUsageOpen(true); }, usage: meterOf };

  return (
    <div className="min-h-screen md:h-screen flex bg-sidebar text-foreground">
      <Sidebar folded={folded} onToggleFold={toggleFold} {...common} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/* A phone has no sidebar: this strip only opens the drawer. */}
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-white/10 bg-sidebar px-3 text-white md:hidden">
          <Logo variant="full" markClass="h-7" />
          <button ref={mobileToggleRef} type="button" onClick={() => setMobileOpen(true)} className={`flex h-9 items-center gap-2 rounded-lg px-3 text-sm text-sidebar-muted hover:bg-white/10 hover:text-white ${FOCUS}`} aria-haspopup="dialog" aria-expanded={mobileOpen} aria-label="Ouvrir la navigation" data-testid="mobile-nav-toggle"><List size={18} /> Menu</button>
        </header>
        <main className="grid-bg min-h-0 flex-1 overflow-y-auto" data-testid="main">
          <Outlet />
        </main>
        <Footer />
      </div>
      {mobileOpen && (
        <>
          <button type="button" className="fixed inset-0 z-[1000] bg-black/60 md:hidden" onClick={() => setMobileOpen(false)} aria-label="Fermer le menu" />
          <div ref={mobileDialogRef} role="dialog" aria-modal="true" aria-label="Navigation mobile" className="fixed inset-0 z-[1001] md:hidden">
            <Sidebar mobile folded={false} closeRef={mobileCloseRef} onClose={() => setMobileOpen(false)} onNavigate={() => setMobileOpen(false)} {...common} />
          </div>
        </>
      )}
      {paletteOpen && <Suspense fallback={null}><CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} onRun={run} /></Suspense>}
      {aiOpen && <Suspense fallback={null}><AIComposerModal open={aiOpen} onClose={() => setAiOpen(false)} /></Suspense>}
      {usageOpen && <Suspense fallback={null}><UsageDialog open={usageOpen} onOpenChange={setUsageOpen} /></Suspense>}
    </div>
  );
}
