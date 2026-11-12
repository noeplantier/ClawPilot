import { useState } from "react";
import { toast } from "sonner";
import { ArrowsClockwise, Calendar } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, dashboardApi, outboundApi, useAsync } from "@/lib/outreach";
import { LIVE_MS } from "@/lib/live";
import { describeApiError } from "@/lib/outreachFormat";
import { ErrorBlock, LoadingBlock } from "@/components/outreach/States";
import FocusPanel from "@/components/outreach/FocusPanel";
import {
  ActivityChart,
  CampaignHealth,
  ConversionFunnel,
  GeoDistribution,
  Inbox,
  KpiStrip,
  LimitsCompliance,
  LiveSignals,
  QualificationBreakdown,
  TopSignals,
  Widget,
} from "@/components/dashboard/Widgets";

const DATE_RANGES = [
  { label: "Today", days: 1 },
  { label: "Last 7 days", days: 7 },
  { label: "Last 14 days", days: 14 },
  { label: "Last 30 days", days: 30 },
  { label: "Last 90 days", days: 90 },
];

export default function Dashboard() {
  const { user } = useAuth();
  const [selectedRange, setSelectedRange] = useState(14);
  const [busy, setBusy] = useState(false);

  // Live query: updates when selectedRange changes
  const page = useAsync(
    () => dashboardApi.overview(selectedRange),
    [selectedRange],
    { key: `dashboard:${selectedRange}`, intervalMs: LIVE_MS }
  );
  const { reload } = page;

  const togglePause = async () => {
    setBusy(true);
    try {
      const paused = !page.data.limits.paused;
      await outboundApi.putLimits({ sending_paused: paused });
      toast.success(paused ? "Sending paused for this organisation" : "Sending resumed");
      await reload();
    } catch (err) {
      toast.error(describeApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const d = page.data;
  return (
    <div className="p-6 md:p-10 space-y-6" data-testid="dashboard-page">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="mono-accent inline-flex items-center gap-2">
            <span className="pos-live-dot" aria-hidden="true" /> // plantiers.outreachos · live command center
          </div>
          <h1 className="text-4xl font-black tracking-tighter">Dashboard</h1>
          <p className="text-soft mt-1 max-w-2xl">
            Commercial intelligence and operational overview. Every figure comes from your own verified data.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Date range filter */}
          <div className="flex items-center rounded-xl bg-white/[0.04] border border-white/10 p-1" data-testid="dashboard-date-filter">
            <Calendar size={14} className="text-brand-lilac ml-2 mr-1" />
            {DATE_RANGES.map((r) => (
              <button
                key={r.days}
                onClick={() => setSelectedRange(r.days)}
                className={`px-2.5 py-1 text-xs rounded-lg transition-all ${
                  selectedRange === r.days
                    ? "bg-brand-500 text-white font-medium shadow-[0_0_12px_rgba(124,58,237,0.5)]"
                    : "text-white/70 hover:text-white hover:bg-white/[0.06]"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>

          <button className="btn-ghost" onClick={reload} disabled={page.loading} data-testid="dashboard-refresh">
            <ArrowsClockwise size={14} className={page.loading ? "animate-spin" : ""} /> REFRESH
          </button>
        </div>
      </div>

      {d?.kpis?.pending_review > 0 && (
        <Link
          to="/app/prospects/review"
          className="surface flex flex-wrap items-center justify-between gap-3 p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-violet hover:border-brand-400/40"
          data-testid="dashboard-review-action"
        >
          <span>
            <strong>{d.kpis.pending_review} prospects awaiting review</strong>
            <span className="block text-sm text-muted-foreground">
              Check their sources and decide what belongs in your CRM.
            </span>
          </span>
          <span className="btn-primary">OPEN REVIEW QUEUE</span>
        </Link>
      )}

      <FocusPanel />

      {page.loading && !d && <LoadingBlock label="Reading your data…" />}
      {page.error && <ErrorBlock message={page.error} onRetry={reload} />}

      {d && (
        <>
          <KpiStrip kpis={d.kpis} limits={d.limits} />

          <div className="grid xl:grid-cols-3 gap-4">
            <div className="xl:col-span-2 space-y-4">
              <Widget title="Sends and replies" kicker={`// last ${selectedRange} days`} testId="widget-activity">
                <ActivityChart series={d.series} />
              </Widget>

              <div className="grid md:grid-cols-2 gap-4">
                <Widget title="Conversion funnel" kicker="// lead pipeline" testId="widget-funnel">
                  <ConversionFunnel kpis={d.kpis} />
                </Widget>
                <Widget title="Lead qualification" kicker="// tiers breakdown" testId="widget-qualification">
                  <QualificationBreakdown kpis={d.kpis} />
                </Widget>
              </div>

              <Widget title="Live discoveries" kicker="// latest prospects and detected signals" testId="widget-signals">
                <LiveSignals prospects={d.latest_prospects} signals={d.latest_signals} />
              </Widget>

              <Widget title="Campaign health" kicker="// per campaign" testId="widget-campaigns">
                <CampaignHealth campaigns={d.campaigns} />
              </Widget>
            </div>

            <div className="space-y-4">
              <Widget
                title="Limits & compliance"
                kicker="// quotas · kill switch · pause · allowlist"
                testId="widget-limits"
              >
                <LimitsCompliance
                  limits={d.limits}
                  canEdit={canDecide(user)}
                  busy={busy}
                  onTogglePause={togglePause}
                />
              </Widget>

              <Widget title="Top signals" kicker="// prospects per detected signal" testId="widget-top-signals">
                <TopSignals items={d.top_signals} />
              </Widget>

              <Widget title="Geographic distribution" kicker="// where your prospects are" testId="widget-geo">
                <GeoDistribution geo={d.geography} />
              </Widget>

              <Widget title="Inbox" kicker="// latest replies" testId="widget-inbox">
                <Inbox items={d.inbox} />
              </Widget>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
