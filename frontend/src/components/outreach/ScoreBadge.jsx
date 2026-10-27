import { coverageLabel, scoreBand } from "@/lib/outreachFormat";

const BAND_STYLE = {
  high: "bg-brand-violet text-white border-white/20",
  medium: "bg-white/[0.04] text-foreground border-white/30",
  low: "bg-card text-soft border-border",
  none: "bg-card text-faint border-dashed border-border",
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
            <span className="text-[10px]">/100</span>
          </>
        )}
      </span>
      {showCoverage && score !== null && score !== undefined && (
        <span className="mono-accent text-soft mt-1" title="Share of the weighted signals that could be observed">
          coverage {coverageLabel(coverage)}
        </span>
      )}
    </span>
  );
}
