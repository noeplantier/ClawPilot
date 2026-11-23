import { dashboardApi } from "@/lib/outreach";
import { useLive } from "@/lib/live";
import { campaignBars, liveLine, pulseHasActivity, pulseTiles } from "@/lib/hubFormat";
import { modeOf } from "@/lib/dashboardFormat";
import { ActivityChart, Widget } from "@/components/dashboard/Widgets";
import { HBarChart } from "@/components/charts/SvgCharts";
import { ErrorBlock } from "@/components/outreach/States";

export const PULSE_MS = 10000;

// The live head of the « Campagnes » page: one line of facts (what really left today against the limits, replies, bounces,
// opt-outs), then the last 14 days and the campaigns by messages sent, only when something was sent: an empty period is one
// sentence, not two empty charts. Everything is read from GET /dashboard/overview, refreshed every 10 s while the tab is visible.
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
      <dl className="flex flex-wrap gap-x-6 gap-y-2 border-y border-border py-3 text-sm" data-testid="pulse-tiles" aria-label="Chiffres du jour">
        {pulseTiles(d).map((t) => (
          <div key={t.key} data-testid={`pulse-${t.key}`}>
            <dt className="inline text-faint">{t.label} : </dt>
            <dd className="inline">
              <span className="font-mono font-semibold" data-testid={`pulse-${t.key}-value`}>{t.value}</span>
              <span className="text-soft"> ({t.hint})</span>
            </dd>
          </div>
        ))}
      </dl>
      {!pulseHasActivity(d) ? (
        <p className="text-sm text-soft" data-testid="pulse-quiet">Aucun envoi sur 14 jours : les graphiques apparaîtront au premier message.</p>
      ) : (
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
      )}
    </section>
  );
}
