import { Link } from "react-router-dom";
import { MapTrifold } from "@phosphor-icons/react";
import { zoneSummary } from "@/lib/mapSearch";

// The perimeter that is really searched, then what the sources really covered: never "all the establishments".
export default function ZoneBlock({ zone, coverage }) {
  return (
    <section aria-label="Zone" className="rounded-2xl border border-border bg-card p-4" data-testid="journey-zone">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mono-accent">// zone{zone.label ? ` · ${zone.label}` : ""}</div>
          <p className="mt-1 text-sm" data-testid="journey-zone-text">{zoneSummary(zone)}</p>
        </div>
        <Link to="/app/map" className="btn-ghost shrink-0" data-testid="journey-back-to-map"><MapTrifold size={14} /> CARTE</Link>
      </div>
      {coverage && (
        <p className={`mt-2 text-sm ${coverage.searched ? "text-soft" : "text-amber-300"}`} data-testid="journey-coverage">{coverage.statement}</p>
      )}
    </section>
  );
}
