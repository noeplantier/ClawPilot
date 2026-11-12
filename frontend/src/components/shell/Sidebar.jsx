import { Link, useLocation } from "react-router-dom";
import { CaretLeft, CaretRight, Command, Gear, MapTrifold, PaperPlaneTilt, SignOut, Sparkle, SquaresFour, Stack, Users, X } from "@phosphor-icons/react";
import Logo from "@/components/Logo";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { SECTIONS, activeTab, sectionOf } from "@/lib/sections";
import { prefetchPath } from "@/lib/routes";

const ICONS = { SquaresFour, MapTrifold, Users, Stack, PaperPlaneTilt, Gear };
export const FOCUS = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400";
const ROW = `relative flex items-center rounded-xl text-sm transition-colors motion-reduce:transition-none ${FOCUS}`;

// A folded entry has no visible label: a real tooltip (hover and keyboard focus), plus the accessible name, tells where it goes.
function Hint({ label, when, children }) {
  if (!when) return children;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right" className="bg-popover text-popover-foreground border border-border">{label}</TooltipContent>
    </Tooltip>
  );
}

// Exactly six entries. The one you are in unfolds its screens right under it (the former top tabs): nothing else is shown.
function Nav({ folded, onNavigate, testPrefix }) {
  const { pathname, search } = useLocation();
  const current = sectionOf(pathname);
  return (
    <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-3" aria-label="Navigation principale">
      <ul className="space-y-1">
        {SECTIONS.map((section) => {
          const Icon = ICONS[section.icon];
          const active = current && current.id === section.id;
          const tab = active ? activeTab(section, pathname, search) : null;
          return (
            <li key={section.id}>
              <Hint label={section.label} when={folded}>
                <Link
                  to={section.to}
                  onClick={onNavigate}
                  onMouseEnter={() => prefetchPath(section.to)}
                  onFocus={() => prefetchPath(section.to)}
                  aria-label={folded ? section.label : undefined}
                  aria-current={active && !tab ? "page" : active ? "true" : undefined}
                  data-testid={`${testPrefix}nav-${section.id}`}
                  className={`${ROW} min-h-11 [@media(max-height:620px)]:min-h-9 ${folded ? "justify-center" : "gap-3 px-3"} ${active ? "bg-brand-violet/20 text-white" : "text-sidebar-muted hover:bg-white/[0.06] hover:text-white"}`}
                >
                  {active && <span aria-hidden="true" className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-brand-400" />}
                  <Icon size={19} weight="duotone" />
                  {!folded && <span className="shell-label font-medium">{section.label}</span>}
                </Link>
              </Hint>
              {active && !folded && (
                <ul className="shell-label ml-[1.45rem] mt-1 space-y-0.5 border-l border-white/10 pl-3" aria-label={`${section.label} : écrans`} data-testid={`${testPrefix}subnav`}>
                  {section.tabs.map((item) => {
                    const here = tab && tab.to === item.to;
                    return (
                      <li key={item.to}>
                        <Link
                          to={item.to}
                          onClick={onNavigate}
                          onMouseEnter={() => prefetchPath(item.to)}
                          onFocus={() => prefetchPath(item.to)}
                          aria-current={here ? "page" : undefined}
                          data-testid={`${testPrefix}${item.testId}`}
                          className={`${ROW} min-h-9 px-3 text-[13px] [@media(max-height:620px)]:min-h-8 ${here ? "text-white" : "text-sidebar-muted hover:bg-white/[0.06] hover:text-white"}`}
                        >
                          {here && <span aria-hidden="true" className="absolute -left-[13px] top-2 bottom-2 w-[2px] rounded-full bg-brand-300" />}
                          {item.label}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function FooterButton({ icon: Icon, label, folded, onClick, testId, hint, ...rest }) {
  return (
    <Hint label={hint || label} when={folded}>
      <button
        type="button"
        onClick={onClick}
        aria-label={folded ? label : undefined}
        data-testid={testId}
        className={`${ROW} min-h-9 w-full text-sidebar-muted hover:bg-white/[0.06] hover:text-white ${folded ? "justify-center" : "gap-2 px-2"}`}
        {...rest}
      >
        <Icon size={16} />
        {!folded && <span className="shell-label truncate">{label}</span>}
      </button>
    </Hint>
  );
}

// The sidebar: the logo centred in the width that is open (the compact mark when folded), the six entries, then the tools
// that were in the top bar (go-to palette, AI composer), the fold button and the account.
export default function Sidebar({ folded, mobile = false, user, org, onToggleFold, onClose, onPalette, onCompose, onLogout, onNavigate, closeRef }) {
  const narrow = folded && !mobile;
  const prefix = mobile ? "mobile-" : "";
  return (
    <TooltipProvider delayDuration={150}>
      <aside
        id={mobile ? undefined : "app-sidebar"}
        className={`shell-aside ${mobile ? "flex fixed inset-y-0 left-0 z-[1001] w-[min(20rem,86vw)] shadow-2xl" : `hidden md:flex ${narrow ? "w-[4.5rem]" : "w-64"} sticky top-0 h-screen`} shrink-0 flex-col overflow-y-auto bg-sidebar text-white border-r border-white/10 transition-[width] duration-200 motion-reduce:transition-none`}
        data-testid={mobile ? "mobile-drawer" : "sidebar"}
        data-folded={!mobile && folded}
        aria-label="Navigation Plantiers OutreachOS"
      >
        <div className="relative flex min-h-[4.5rem] items-center justify-center border-b border-white/10 px-3 [@media(max-height:620px)]:min-h-[3.5rem]" data-testid={`${prefix}brand`}>
          <Link to="/app/dashboard" onClick={onNavigate} aria-label="Plantiers OutreachOS, vue d’ensemble" className={`rounded-lg ${FOCUS}`}>
            <Logo variant={narrow ? "mark" : "full"} markClass="h-9" />
          </Link>
          {mobile && (
            <button ref={closeRef} type="button" onClick={onClose} className={`absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-sidebar-muted hover:bg-white/10 hover:text-white ${FOCUS}`} aria-label="Fermer la navigation">
              <X size={18} />
            </button>
          )}
        </div>
        <Nav folded={narrow} onNavigate={onNavigate} testPrefix={prefix} />
        <div className="space-y-1 border-t border-white/10 p-3" data-testid={`${prefix}tools`}>
          <FooterButton icon={Command} label="Aller à… (Ctrl K)" hint="Aller à… (Ctrl ou Cmd + K)" folded={narrow} onClick={onPalette} testId={`${prefix}open-palette`} aria-haspopup="dialog" />
          <FooterButton icon={Sparkle} label="Composer IA" folded={narrow} onClick={onCompose} testId={`${prefix}open-ai-composer`} aria-haspopup="dialog" />
          {!mobile && (
            <FooterButton
              icon={narrow ? CaretRight : CaretLeft}
              label={narrow ? "Déplier la navigation" : "Replier la navigation"}
              hint="Déplier la navigation ([)"
              folded={narrow}
              onClick={onToggleFold}
              testId="sidebar-toggle"
              aria-expanded={!folded}
              aria-controls="app-sidebar"
              title={narrow ? undefined : "Replier la navigation ([)"}
            />
          )}
        </div>
        <div className={`border-t border-white/10 p-3 ${narrow ? "flex flex-col items-center" : ""}`} data-testid={`${prefix}account`}>
          {!narrow && (
            <div className="px-2 pb-2 [@media(max-height:620px)]:hidden">
              <div className="truncate text-sm font-medium text-white" data-testid={`${prefix}org-name`}>{org?.name || "—"}</div>
              <div className="truncate font-mono text-[11px] text-sidebar-muted" data-testid={`${prefix}user-email`}>{user?.email}</div>
            </div>
          )}
          <FooterButton icon={SignOut} label="Déconnexion" hint={`Déconnexion (${user?.email || ""})`} folded={narrow} onClick={onLogout} testId={`${prefix}logout-button`} />
        </div>
      </aside>
    </TooltipProvider>
  );
}
