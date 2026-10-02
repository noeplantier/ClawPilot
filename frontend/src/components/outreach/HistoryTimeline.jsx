import { detailSummary, formatDateTime } from "@/lib/outreachFormat";

export default function HistoryTimeline({ items }) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-[#6B6B66]" data-testid="history-empty">Nothing has happened to this prospect yet.</p>;
  }
  return (
    <ol className="space-y-2" data-testid="history-list">
      {items.map((e) => (
        <li key={e.key} className="flex gap-3 text-sm border-l-2 border-[#D6D3C8] pl-3" data-testid="history-item">
          <div className="min-w-0">
            <div className="font-medium">{e.label}</div>
            <div className="mono-accent text-[#6B6B66]">
              {formatDateTime(e.at)} · {e.actor}
            </div>
            {detailSummary(e.detail) && <div className="text-xs text-[#475569] mt-0.5 break-words">{detailSummary(e.detail)}</div>}
            {e.detail && e.detail.excerpt && (
              <blockquote className="text-xs text-[#475569] mt-1 pl-2 border-l border-[#D6D3C8] whitespace-pre-wrap">{e.detail.excerpt}</blockquote>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
