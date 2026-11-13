import { dashboardApi } from "@/lib/outreach";
import { useLive } from "@/lib/live";
import { campaignBars, liveLine, pulseTiles } from "@/lib/hubFormat";
import { modeOf } from "@/lib/dashboardFormat";
import { ActivityChart, Widget } from "@/components/dashboard/Widgets";
import { HBarChart } from "@/components/charts/SvgCharts";
import { ErrorBlock } from "@/components/outreach/States";

export const PULSE_MS = 10000;

// The live head of the « Campagnes » page: what really left today against the limits, replies and bounces, the last 14 days and
// the campaigns by messages sent. Everything is read from GET /dashboard/overview and refreshed every 10 s while the tab is visible.
export default function CampaignPulse() {
  const live = useLive(() => dashboardApi.overview(14), [], { intervalMs: PULSE_MS, idOf: () => "pulse", itemsOf: (d) => [d], key: "campaigns:pulse" });
  const d = live.data;
  if (live.error && !d) return <ErrorBlock message={live.error} onRetry={live.reload} />;
  if (!d) return <p role="status" className="surface p-4 text-sm" data-testid="pulse-loading">Chargement des chiffres en direct…</p>;
  const mode = modeOf(d.limits);
  const bars = campaignBars(d.campaigns);
  return (
    <section aria-label="Activité en direct" className="space-y-4" data-testid="campaign-pulse">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="inline-flex items-center gap-2 text-xs text-brand-lilac" role="status" aria-live="polite" data-testid="pulse-live">
          <span className="pos-live-dot" aria-hidden="true" />
          {liveLine({ updatedAt: live.updatedAt, stale: live.stale, intervalMs: PULSE_MS })}
        </p>
        <span className={`chip chip-${mode.tone}`} data-testid="pulse-mode">{mode.label}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5" data-testid="pulse-tiles">
        {pulseTiles(d).map((t) => (
          <div key={t.key} className="surface rounded-xl p-4" data-testid={`pulse-${t.key}`}>
            <div className="mono-accent">{t.label}</div>
            <div className="mt-1 font-display text-2xl font-black tracking-tight" data-testid={`pulse-${t.key}-value`}>{t.value}</div>
            <div className="mt-1 truncate text-xs text-soft">{t.hint}</div>
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Widget title="Envois et réponses, 14 jours" kicker="En direct" testId="pulse-activity">
            <ActivityChart series={d.series} />
          </Widget>
        </div>
        <div className="lg:col-span-2">
          <Widget title="Campagnes par messages envoyés" kicker="En direct" testId="pulse-campaigns">
            {bars.length ? <HBarChart items={bars} label="Messages envoyés par campagne" /> : <p className="text-sm text-soft" data-testid="pulse-campaigns-empty">Aucune campagne n&apos;a encore envoyé de message.</p>}
          </Widget>
        </div>
      </div>
    </section>
  );
}
