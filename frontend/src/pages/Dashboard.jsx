import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowsClockwise } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, dashboardApi, outboundApi, useAsync } from "@/lib/outreach";
import { describeApiError } from "@/lib/outreachFormat";
import { ErrorBlock, LoadingBlock } from "@/components/outreach/States";
import { ActivityChart, CampaignHealth, Inbox, KpiStrip, LimitsCompliance, LiveSignals, Widget } from "@/components/dashboard/Widgets";

const REFRESH_MS = 30000;

export default function Dashboard() {
  const { user } = useAuth();
  const page = useAsync(() => dashboardApi.overview(), []);
  const [busy, setBusy] = useState(false);
  const { reload } = page;

  // "Live": refresh every 30 s while the tab is visible, keeping what is on screen until the new data arrives.
  useEffect(() => {
    const id = setInterval(() => { if (!document.hidden) reload(); }, REFRESH_MS);
    return () => clearInterval(id);
  }, [reload]);

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
          <p className="text-[#6B6B66] mt-1 max-w-2xl">Every figure comes from your own data. A dash means nothing is known yet, not zero.</p>
        </div>
        <button className="btn-ghost" onClick={reload} disabled={page.loading} data-testid="dashboard-refresh"><ArrowsClockwise size={14} /> REFRESH</button>
      </div>

      {page.loading && !d && <LoadingBlock label="Reading your data…" />}
      {page.error && <ErrorBlock message={page.error} onRetry={reload} />}

      {d && (
        <>
          <KpiStrip kpis={d.kpis} limits={d.limits} />
          <div className="grid xl:grid-cols-3 gap-4">
            <div className="xl:col-span-2 space-y-4">
              <Widget title="Sends and replies" kicker="// last 14 days" testId="widget-activity"><ActivityChart series={d.series} /></Widget>
              <Widget title="Live signals" kicker="// latest prospects and detected signals" testId="widget-signals">
                <LiveSignals prospects={d.latest_prospects} signals={d.latest_signals} />
              </Widget>
              <Widget title="Campaign health" kicker="// per campaign" testId="widget-campaigns"><CampaignHealth campaigns={d.campaigns} /></Widget>
            </div>
            <div className="space-y-4">
              <Widget title="Limits & compliance" kicker="// quotas · kill switch · pause · allowlist" testId="widget-limits">
                <LimitsCompliance limits={d.limits} canEdit={canDecide(user)} busy={busy} onTogglePause={togglePause} />
              </Widget>
              <Widget title="Inbox" kicker="// latest replies" testId="widget-inbox"><Inbox items={d.inbox} /></Widget>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
