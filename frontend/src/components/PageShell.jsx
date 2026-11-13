// The one composition of an application page: a title, its main action, the essential content, and the details on demand.
// A page that needs the whole window (the map) does not use it; every other page puts its content in this container
// instead of stacking its own cards, so the screens read alike and the technical detail never competes with the task.
// `embedded`: the screen is one tab of a merged page that already has the title; only its action and content are drawn.
export default function PageShell({ title, kicker, lead, action, children, details, detailsLabel = "Détails techniques", testId, width = "max-w-5xl", embedded = false }) {
  if (embedded) {
    return (
      <div className="space-y-6" data-testid={testId}>
        {action && <div className="flex flex-wrap items-center justify-end gap-2">{action}</div>}
        <div className="space-y-8">{children}</div>
        {details && (
          <details className="rounded-xl border border-border bg-card/60 px-4 py-3 text-sm" data-testid="page-details">
            <summary className="cursor-pointer select-none font-mono text-xs uppercase tracking-[0.18em] text-soft">{detailsLabel}</summary>
            <div className="mt-3 space-y-3">{details}</div>
          </details>
        )}
      </div>
    );
  }
  return (
    <div className={`mx-auto w-full ${width} px-4 py-6 md:px-8 md:py-8`} data-testid={testId}>
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-border pb-4">
        <div className="min-w-0">
          {kicker && <div className="mono-accent">{`// ${kicker}`}</div>}
          <h1 className="text-3xl font-black tracking-tighter leading-tight md:text-4xl">{title}</h1>
          {lead && <p className="mt-1 max-w-2xl text-sm text-soft">{lead}</p>}
        </div>
        {action && <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div>}
      </header>
      <div className="mt-6 space-y-8">{children}</div>
      {details && (
        <details className="mt-10 rounded-xl border border-border bg-card/60 px-4 py-3 text-sm" data-testid="page-details">
          <summary className="cursor-pointer select-none font-mono text-xs uppercase tracking-[0.18em] text-soft">{detailsLabel}</summary>
          <div className="mt-3 space-y-3">{details}</div>
        </details>
      )}
    </div>
  );
}
