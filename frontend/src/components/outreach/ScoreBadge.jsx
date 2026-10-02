import { coverageLabel, scoreBand } from "@/lib/outreachFormat";

const BAND_STYLE = {
  high: "bg-[#0F172A] text-white border-[#0F172A]",
  medium: "bg-[#F1F5F9] text-[#0F172A] border-[#0F172A]/30",
  low: "bg-white text-[#475569] border-[#D6D3C8]",
  none: "bg-white text-[#999995] border-dashed border-[#D6D3C8]",
};

// The number is always printed: colour only reinforces it. `null` means "never scored", not zero.
export default function ScoreBadge({ score, coverage, showCoverage = false }) {
  const band = scoreBand(score);
  return (
    <span className="inline-flex flex-col items-start leading-tight" data-testid="score-badge">
      <span className={`inline-flex items-baseline gap-1 px-2 py-0.5 border rounded-md font-mono ${BAND_STYLE[band]}`}>
        {score === null || score === undefined ? (
          <span className="text-xs">not scored</span>
        ) : (
          <>
            <span className="text-base font-bold">{score}</span>
            <span className="text-[10px] opacity-70">/100</span>
          </>
        )}
      </span>
      {showCoverage && score !== null && score !== undefined && (
        <span className="mono-accent text-[#6B6B66] mt-1" title="Share of the weighted signals that could be observed">
          coverage {coverageLabel(coverage)}
        </span>
      )}
    </span>
  );
}
