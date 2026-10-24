import { Eye, EyeSlash } from "@phosphor-icons/react";
import { emptyNote } from "@/lib/heat";

// Says how many empty leads (no e-mail, phone or website) a list leaves out, and lets the person bring them back. Nothing is
// rendered when there is none: no control without a reason.
export default function EmptyToggle({ empty, showEmpty, onToggle, testId = "empty-toggle" }) {
  const note = emptyNote(empty, showEmpty);
  if (!note) return null;
  return (
    <span className="inline-flex items-center gap-2 text-xs text-[#5F5F5A]" data-testid={`${testId}-bar`}>
      <span role="status" aria-live="polite" data-testid={`${testId}-note`}>{note}</span>
      <button type="button" className="btn-ghost !py-0.5 !px-2 text-xs" onClick={onToggle} aria-pressed={showEmpty} data-testid={testId}>
        {showEmpty ? <EyeSlash size={12} /> : <Eye size={12} />} {showEmpty ? "HIDE THEM" : "SHOW THEM"}
      </button>
    </span>
  );
}
