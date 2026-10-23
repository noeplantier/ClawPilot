import { Link } from "react-router-dom";
import { CheckCircle, X } from "@phosphor-icons/react";
import { describeAdded } from "@/lib/mapQuickAdd";

// What really happened after "add to CRM", kept on screen until it is closed (the pin and its popup are rebuilt as soon as the
// business becomes one of my prospects, so the answer cannot live inside the popup).
export default function AddedCard({ out, siteAsked, onClose, className = "" }) {
  return (
    <div className={`rounded-2xl border border-emerald-500/40 bg-white/90 backdrop-blur-xl shadow-xl p-3 text-xs space-y-1 max-w-sm ${className}`} role="status" data-testid="place-added">
      <div className="flex items-start justify-between gap-2">
        <span className="font-display font-bold text-sm inline-flex items-center gap-1.5"><CheckCircle size={16} weight="fill" className="text-emerald-600" /> {out.in_crm ? "In your CRM" : "Waiting for review"}</span>
        <button className="btn-ghost !px-1.5 !py-0.5" onClick={onClose} aria-label="Close" data-testid="place-added-close"><X size={12} /></button>
      </div>
      {describeAdded(out, { siteAsked }).map((line) => <p key={line}>{line}</p>)}
      <div className="flex gap-3 pt-1">
        <Link to="/app/leads" className="underline font-semibold" data-testid="place-open-crm">Open the CRM</Link>
        <Link to={`/app/prospects/${out.lead_id}`} className="underline" data-testid="place-open-prospect">Open the prospect</Link>
      </div>
    </div>
  );
}
