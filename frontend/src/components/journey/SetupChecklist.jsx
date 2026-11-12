import { Link } from "react-router-dom";
import { CheckCircle, Warning, WarningCircle } from "@phosphor-icons/react";
import { readinessView } from "@/lib/journeyFormat";

// The one-time setup as a short list. Once everything required is in place it folds into one line: the person is never asked again.
export default function SetupChecklist({ readiness }) {
  const view = readinessView(readiness);
  const problems = [...view.blockers, ...view.warnings];
  if (problems.length === 0) {
    return (
      <p className="flex items-center gap-2 text-sm text-soft" data-testid="setup-ready">
        <CheckCircle size={18} weight="fill" className="text-emerald-400" aria-hidden="true" />
        Configuration prête ({view.done}/{view.total}).
        {view.notes.length > 0 && <span className="text-faint"> {view.notes[0].note}</span>}
      </p>
    );
  }
  return (
    <section aria-label="Configuration à terminer" className="rounded-2xl border border-border bg-card p-4" data-testid="setup-checklist">
      <h2 className="font-display text-lg font-bold">{view.blockers.length > 0 ? "À faire une seule fois avant d'approuver" : "À savoir avant d'approuver"}</h2>
      <ul className="mt-3 space-y-3">
        {problems.map((item) => {
          const Icon = item.blocking ? WarningCircle : Warning;
          return (
            <li key={item.id} className="flex gap-3 text-sm" data-testid={`setup-${item.id}`}>
              <Icon size={20} weight="fill" aria-hidden="true" className={item.blocking ? "mt-0.5 shrink-0 text-red-400" : "mt-0.5 shrink-0 text-amber-300"} />
              <div className="min-w-0">
                <div className="font-medium">{item.label}{item.blocking ? "" : " (ne bloque pas)"}</div>
                {item.fix && <p className="text-soft">{item.fix}</p>}
                {item.note && <p className="text-faint">{item.note}</p>}
                {item.link && <Link to={item.link} className="underline text-brand-lilac" data-testid={`setup-link-${item.id}`}>Ouvrir le réglage</Link>}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
