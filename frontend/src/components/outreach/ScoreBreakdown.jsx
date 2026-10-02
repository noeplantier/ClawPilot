import StateChip from "@/components/outreach/StateChip";
import { coverageLabel, explainTotal, formatDateTime } from "@/lib/outreachFormat";

// "Why this score": one row per signal with its weight, the points it earned and the evidence behind it.
export default function ScoreBreakdown({ detail }) {
  if (!detail) {
    return (
      <p className="text-sm text-[#6B6B66]" data-testid="score-empty">
        This prospect has not been scored yet. Run discovery or recompute the score.
      </p>
    );
  }
  const total = explainTotal(detail.breakdown);
  return (
    <div className="space-y-3" data-testid="score-breakdown">
      <p className="text-sm text-[#475569]">
        The score is the sum of the points of <strong>detected</strong> signals, kept between 0 and 100. Signals that are
        <em> not detected</em> or <em>unknown</em> add nothing and never subtract: a missing observation is not a defect.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAF7] border-b border-[#D6D3C8]">
            <tr className="text-left mono-accent">
              <th className="p-2">signal</th>
              <th className="p-2">state</th>
              <th className="p-2 text-right">weight</th>
              <th className="p-2 text-right">points</th>
              <th className="p-2">evidence</th>
            </tr>
          </thead>
          <tbody>
            {detail.breakdown.map((line) => (
              <tr key={line.signal} className="border-b border-[#EDEBE0] align-top" data-testid={`breakdown-${line.signal}`}>
                <td className="p-2 font-medium">{line.label}</td>
                <td className="p-2 whitespace-nowrap">
                  <StateChip state={line.state} />
                </td>
                <td className="p-2 text-right font-mono text-[#6B6B66]">{line.weight}</td>
                <td className="p-2 text-right font-mono font-bold">{line.points}</td>
                <td className="p-2 text-[#475569]">{line.explanation}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-[#FAFAF7]">
              <td className="p-2 font-bold" colSpan={3}>
                Total
              </td>
              <td className="p-2 text-right font-mono font-bold" data-testid="score-total">
                {detail.score}
              </td>
              <td className="p-2 text-[#6B6B66]">
                {total.clamped ? `${total.raw} raw points, capped to ${total.capped}. ` : ""}
                {total.observed} of {total.weighted} weighted signals could be observed (coverage {coverageLabel(detail.coverage)}).
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="mono-accent text-[#999995]">
        // config v{detail.version} “{detail.config_label}” · hash {detail.config_hash} · computed {formatDateTime(detail.computed_at)}
      </p>
    </div>
  );
}
