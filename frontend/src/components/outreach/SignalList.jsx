import StateChip from "@/components/outreach/StateChip";
import { formatDateTime } from "@/lib/outreachFormat";

export default function SignalList({ signals }) {
  if (!signals || signals.length === 0) {
    return <p className="text-sm text-[#5F5F5A]">No signal has been recorded for this prospect.</p>;
  }
  return (
    <ul className="grid md:grid-cols-2 gap-3" data-testid="signal-list">
      {signals.map((s) => (
        <li key={s.key} className="border border-[#D6D3C8] rounded-md p-3 bg-white" data-testid={`signal-${s.key}`}>
          <div className="flex items-center justify-between gap-2">
            <span className="font-display font-semibold text-sm">{s.label}</span>
            <StateChip state={s.state} />
          </div>
          <p className="text-sm text-[#475569] mt-2">{s.evidence}</p>
          <p className="mono-accent text-[#6B6B66] mt-2">observed {formatDateTime(s.observed_at)}</p>
        </li>
      ))}
    </ul>
  );
}
