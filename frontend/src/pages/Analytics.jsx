import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hasAnyValue } from "@/lib/chartMath";
import { AreaLineChart, HBarChart, VBarChart } from "@/components/charts/SvgCharts";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

function Panel({ kicker, title, children }) {
  return (
    <section className="surface p-6" aria-label={title}>
      <div className="mono-accent">{kicker}</div>
      <h2 className="font-display font-bold text-lg mt-0.5 mb-4">{title}</h2>
      {children}
    </section>
  );
}

export default function Analytics() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = () => {
    setError(null);
    api.get("/analytics/overview").then((r) => setData(r.data)).catch(() => setError("Could not load the analytics. Try again."));
  };
  useEffect(load, []);

  if (error) return <div className="p-6 md:p-10"><ErrorBlock message={error} onRetry={load} /></div>;
  if (!data) return <div className="p-6 md:p-10"><LoadingBlock label="Loading analytics…" /></div>;

  const totals = data.totals || {};
  const timeseries = data.timeseries || [];
  const pipeline = data.pipeline || {};
  const topCountries = data.top_countries || [];
  const funnel = [
    { name: "Sent", value: totals.sent || 0, fill: "var(--brand-violet)" },
    { name: "Opened", value: totals.opened || 0, fill: "var(--brand-ink)" },
    { name: "Replied", value: totals.replied || 0, fill: "#94A3B8" },
    { name: "Converted", value: totals.converted || 0, fill: "#10B981" },
  ];
  const pipelineMax = Math.max(...Object.values(pipeline), 1);

  return (
    <div className="p-6 md:p-10 space-y-6">
      <div>
        <div className="mono-accent">// deep.analytics</div>
        <h1 className="text-4xl font-black tracking-tighter">Analytics</h1>
        <p className="text-soft mt-1">Cross-channel performance breakdown. Every figure comes from recorded events.</p>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Panel kicker="/// all recorded time" title="Conversion Funnel">
          {funnel.every((f) => f.value === 0)
            ? <EmptyBlock title="Nothing sent yet" testId="funnel-empty"><p>The funnel fills as messages are sent and answered.</p></EmptyBlock>
            : <HBarChart items={funnel} label="Conversion funnel" />}
        </Panel>

        <Panel kicker="/// throughput" title="14-day Velocity">
          {!hasAnyValue(timeseries, ["replied", "opened"])
            ? <EmptyBlock title="No activity in the last 14 days" testId="velocity-empty"><p>Opens and replies appear here once they are recorded.</p></EmptyBlock>
            : <AreaLineChart rows={timeseries} areaKey="replied" lineKey="opened" label="Replies (area) and opens (line) per day" />}
          <p className="mono-accent flex gap-4 mt-1"><span className="text-[var(--brand-ink)]">— replied</span><span className="text-brand-violet">— opened</span></p>
        </Panel>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Panel kicker="/// pipeline.heatmap" title="Pipeline Density">
          {Object.keys(pipeline).length === 0
            ? <EmptyBlock title="No lead in the pipeline" testId="pipeline-empty"><p>Add or import leads to see where they stand.</p></EmptyBlock>
            : (
              <div className="space-y-3">
                {Object.entries(pipeline).map(([stage, count]) => (
                  <div key={stage} className="flex items-center gap-3">
                    <div className="mono-accent w-24">{stage}</div>
                    <div className="flex-1 h-6 bg-white/[0.04] rounded-sm overflow-hidden relative">
                      <div className="h-full bg-gradient-to-r from-brand-violet to-[var(--brand-ink)]" style={{ width: `${(count / pipelineMax) * 100}%` }} />
                      <div className="absolute inset-0 flex items-center justify-end pr-2 font-mono text-xs text-foreground">{count}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
        </Panel>

        <Panel kicker="/// territories" title="Geographic Reach">
          {topCountries.length === 0
            ? <EmptyBlock title="No country recorded" testId="countries-empty"><p>Leads with a country appear here.</p></EmptyBlock>
            : <VBarChart rows={topCountries} labelKey="country" valueKey="leads" label="Leads per country" />}
        </Panel>
      </div>
    </div>
  );
}
