import { useState } from "react";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, systemApi, useAsync } from "@/lib/outreach";
import { describeApiError } from "@/lib/outreachFormat";
import { checks, coolingLine, jobsLine, probeLine } from "@/lib/systemHealth";
import { ErrorBlock, LoadingBlock } from "@/components/outreach/States";

export default function SystemHealth() {
  const { user } = useAuth();
  const page = useAsync(() => systemApi.health(), []);
  const [probe, setProbe] = useState(null);
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState(null);

  const runProbe = async () => {
    setProbing(true);
    setProbeError(null);
    try {
      setProbe(await systemApi.probeOverpass());
    } catch (e) {
      setProbeError(describeApiError(e));
    } finally {
      setProbing(false);
    }
  };

  const d = page.data;
  return (
    <div className="p-6 md:p-10 space-y-6 max-w-4xl" data-testid="system-page">
      <div>
        <div className="mono-accent">// system.health</div>
        <h1 className="text-4xl font-black tracking-tighter">System health</h1>
        <p className="text-[#5F5F5A] mt-1">What this deployment can do right now, measured from the server, not assumed.</p>
      </div>
      {page.loading && !d && <LoadingBlock label="Checking…" />}
      {page.error && <ErrorBlock message={page.error} onRetry={page.reload} />}
      {d && (
        <>
          <ul className="surface divide-y divide-[#E9EEF7]" data-testid="health-checks">
            {checks(d).map((c) => (
              <li key={c.key} className="p-4 flex items-start gap-3" data-testid={`health-${c.key}`} data-ok={c.ok}>
                {c.ok ? <CheckCircle size={20} weight="fill" className="text-[#15803D] shrink-0" /> : <WarningCircle size={20} weight="fill" className="text-[#4338CA] shrink-0" />}
                <div><div className="font-semibold">{c.label}</div><div className="text-sm text-[#5F5F5A]">{c.detail}</div></div>
              </li>
            ))}
          </ul>
          <p className="text-sm" data-testid="health-jobs">{jobsLine(d.map_jobs_24h)}</p>
          <section className="surface p-5 space-y-3" data-testid="health-overpass">
            <h2 className="font-display text-lg font-bold">OpenStreetMap servers</h2>
            <p className="text-sm text-[#5F5F5A]">Public servers used for the map search: {d.overpass.endpoints.join(", ")}. The probe asks each one for its status page from this server.</p>
            {coolingLine(d.overpass.cooling_down) && <p className="text-sm text-[#92400E]" data-testid="health-cooling">{coolingLine(d.overpass.cooling_down)}</p>}
            {canDecide(user) && <button className="btn-ink" onClick={runProbe} disabled={probing} data-testid="probe-run">{probing ? "PROBING…" : "CHECK FROM THE SERVER"}</button>}
            {probeError && <p role="alert" className="text-sm text-[#991B1B]">{probeError}</p>}
            {probe && (
              <ul className="text-sm space-y-1" data-testid="probe-result">
                {probe.servers.map((s) => <li key={s.host} data-ok={s.ok}>{s.ok ? "✓" : "✗"} {probeLine(s)}</li>)}
                {!probe.ok && <li className="text-[#991B1B]">None answered: the server cannot reach OpenStreetMap from here. Searches fall back to your browser.</li>}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
