import { formatDateTime } from "@/lib/outreachFormat";

// Provenance: where every piece of data came from, when, and under what licence note.
export default function SourceList({ sources }) {
  if (!sources || sources.length === 0) {
    return <p className="text-sm text-[#5F5F5A]">No source is recorded (this can happen after an erasure).</p>;
  }
  return (
    <ul className="space-y-3" data-testid="source-list">
      {sources.map((s) => {
        const fields = Object.entries(s.fields || {}).filter(([, v]) => v !== null && v !== "");
        return (
          <li key={s.id} className="border border-[#D6D3C8] rounded-md p-3 bg-white" data-testid="source-item">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <span className="font-display font-semibold text-sm">{s.source_name}</span>
              <span className="mono-accent">listing {s.external_id}</span>
              <span className="mono-accent text-[#6B6B66]">fetched {formatDateTime(s.fetched_at)}</span>
            </div>
            <p className="font-mono text-xs text-[#5F5F5A] mt-1 break-all">{s.source_url}</p>
            <p className="text-xs text-[#475569] mt-1">Licence note: {s.license_note}</p>
            {fields.length > 0 && (
              <details className="mt-2">
                <summary className="mono-accent cursor-pointer">data as published ({fields.length} fields)</summary>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 mt-2 text-xs">
                  {fields.map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="font-mono text-[#6B6B66]">{k}</dt>
                      <dd className="break-words">{String(v)}</dd>
                    </div>
                  ))}
                </dl>
              </details>
            )}
          </li>
        );
      })}
    </ul>
  );
}
