import { useState } from "react";
import { toast } from "sonner";
import { ArrowsClockwise } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, dashboardApi, outboundApi, useAsync } from "@/lib/outreach";
import { LIVE_MS } from "@/lib/live";
import { describeApiError } from "@/lib/outreachFormat";
import { ErrorBlock, LoadingBlock } from "@/components/outreach/States";
import FocusPanel from "@/components/outreach/FocusPanel";
import { ActivityChart, CampaignHealth, GeoDistribution, Inbox, KpiStrip, LimitsCompliance, LiveSignals, TopSignals, Widget } from "@/components/dashboard/Widgets";

export default function Dashboard() {
  const { user } = useAuth();
  // Live: on screen at once from the last answer, refreshed every few seconds while the tab is visible (and when it is shown again).
  const page = useAsync(() => dashboardApi.overview(), [], { key: "dashboard", intervalMs: LIVE_MS });
  const [busy, setBusy] = useState(false);
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
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="mono-accent inline-flex items-center gap-2"><span className="pos-live-dot" aria-hidden="true" /> // plantiers.outreachos · live</div>
          <h1 className="text-4xl font-black tracking-tighter">Dashboard</h1>
          <p className="text-soft mt-1 max-w-2xl">Every figure comes from your own data. A dash means nothing is known yet, not zero.</p>
        </div>
        <button className="btn-ghost" onClick={reload} disabled={page.loading} data-testid="dashboard-refresh"><ArrowsClockwise size={14} /> REFRESH</button>
      </div>

      {d?.kpis?.pending_review > 0 && (
        <Link to="/app/prospects/review" className="surface flex flex-wrap items-center justify-between gap-3 p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-violet" data-testid="dashboard-review-action">
          <span><strong>{d.kpis.pending_review} prospects awaiting review</strong><span className="block text-sm text-muted-foreground">Check their sources and decide what belongs in your CRM.</span></span>
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
              <Widget title="Sends and replies" kicker="// last 14 days" testId="widget-activity"><ActivityChart series={d.series} /></Widget>
              <Widget title="Live discoveries" kicker="// latest prospects and detected signals" testId="widget-signals">
                <LiveSignals prospects={d.latest_prospects} signals={d.latest_signals} />
              </Widget>
              <Widget title="Campaign health" kicker="// per campaign" testId="widget-campaigns"><CampaignHealth campaigns={d.campaigns} /></Widget>
            </div>
            <div className="space-y-4">
              <Widget title="Limits & compliance" kicker="// quotas · kill switch · pause · allowlist" testId="widget-limits">
                <LimitsCompliance limits={d.limits} canEdit={canDecide(user)} busy={busy} onTogglePause={togglePause} />
              </Widget>
              <Widget title="Top signals" kicker="// prospects per detected signal" testId="widget-top-signals"><TopSignals items={d.top_signals} /></Widget>
              <Widget title="Geographic distribution" kicker="// where your prospects are" testId="widget-geo"><GeoDistribution geo={d.geography} /></Widget>
              <Widget title="Inbox" kicker="// latest replies" testId="widget-inbox"><Inbox items={d.inbox} /></Widget>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
