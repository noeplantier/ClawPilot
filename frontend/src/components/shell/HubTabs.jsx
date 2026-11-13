import { Link, useLocation } from "react-router-dom";
import { prefetchPath } from "@/lib/routes";

// The tabs of a merged page (Campagnes, À traiter, Automatisations). Each tab is a real path, so a link, the back button and
// the query of the screen (?id=…) keep working; the tab only swaps the content under one shared header.
// `count` is a number from the API or undefined: nothing is shown rather than an invented 0.
export default function HubTabs({ tabs, label, testId = "hub-tabs" }) {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/$/, "");
  return (
    <nav aria-label={label} data-testid={testId}>
      <ul className="flex flex-wrap gap-1 rounded-2xl border border-border bg-card/60 p-1" role="tablist">
        {tabs.map((t) => {
          const active = here === t.to;
          return (
            <li key={t.to} role="presentation">
              <Link
                to={t.to}
                role="tab"
                aria-selected={active}
                aria-current={active ? "page" : undefined}
                onMouseEnter={() => prefetchPath(t.to)}
                onFocus={() => prefetchPath(t.to)}
                data-testid={t.testId}
                className={`inline-flex min-h-9 items-center gap-2 rounded-xl px-3 text-sm font-display transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 ${
                  active ? "bg-brand-violet text-white" : "text-soft hover:bg-white/[0.06] hover:text-white"
                }`}
              >
                {t.icon}
                <span>{t.label}</span>
                {typeof t.count === "number" && (
                  <span className={`rounded-full px-1.5 font-mono text-[11px] ${active ? "bg-white/20" : "bg-white/[0.06] text-faint"}`} data-testid={`${t.testId}-count`}>
                    {t.count}
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
      {tabs.map((t) => (here === t.to && t.hint ? <p key={t.to} className="mt-2 text-xs text-soft">{t.hint}</p> : null))}
    </nav>
  );
}
