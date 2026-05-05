import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell,
} from "recharts";
import {
  PaperPlaneTilt, Eye, ChatCircleDots, Target, Robot, Users, TrendUp, Lightning, ArrowUpRight, Pulse, CircleNotch,
} from "@phosphor-icons/react";

const METRICS = [
  { key: "sent",      label: "MESSAGES DISPATCHED", icon: PaperPlaneTilt, color: "#DC2626" },
  { key: "opened",    label: "OPENED",              icon: Eye,            color: "#0F172A" },
  { key: "replied",   label: "REPLIED",             icon: ChatCircleDots, color: "#475569" },
  { key: "converted", label: "CONVERTED",           icon: Target,         color: "#10B981" },
];

const CHANNEL_COLORS = ["#DC2626", "#0F172A"];

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [activity, setActivity] = useState([]);
  const [demoRunning, setDemoRunning] = useState(false);
  const [demoResult, setDemoResult] = useState(null);

  const reload = async () => {
    const [a, b] = await Promise.all([
      api.get("/analytics/overview"),
      api.get("/analytics/activity"),
    ]);
    setData(a.data);
    setActivity(b.data);
  };

  useEffect(() => { reload(); }, []);

  const runConversionDemo = async () => {
    setDemoRunning(true);
    setDemoResult(null);
    try {
      const { data: r } = await api.post("/leads/conversion-demo");
      setDemoResult(r);
      toast.success(`🚀 ${r.events_fired} engagement events fired across ${r.leads_touched} leads`);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Demo failed");
    } finally {
      setDemoRunning(false);
    }
  };

  if (!data) {
    return <div className="p-12 text-[#6B6B66] font-mono">loading telemetry...</div>;
  }

  const openRate = data.totals.sent ? ((data.totals.opened / data.totals.sent) * 100).toFixed(1) : "0.0";
  const replyRate = data.totals.sent ? ((data.totals.replied / data.totals.sent) * 100).toFixed(1) : "0.0";

  return (
    <div className="p-6 md:p-10 space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="mono-accent mb-2">// operations.overview</div>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tighter">Command Dashboard</h1>
          <p className="text-[#6B6B66] mt-2">Real-time telemetry across all active outreach operations.</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={runConversionDemo}
            disabled={demoRunning}
            className="btn-primary"
            data-testid="run-conversion-demo"
          >
            {demoRunning ? <><CircleNotch size={14} className="spin-slow" /> RUNNING…</> : <><Pulse size={14} weight="fill" /> RUN CONVERSION DEMO</>}
          </button>
          <span className="chip chip-success"><span className="w-1.5 h-1.5 rounded-full bg-[#10B981] pulse-dot" /> LIVE</span>
          <span className="chip chip-cyan font-mono">{data.agents_running}/{data.agents_total} agents online</span>
        </div>
      </div>

      {demoResult && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="surface bg-[#FEF7F0] border-[#F59E0B]/40 p-5"
          data-testid="demo-result-card"
        >
          <div className="flex items-center gap-2 mb-3">
            <Pulse size={18} weight="fill" className="text-[#DC2626]" />
            <div className="font-display font-bold text-lg">Conversion Engine — Live Run</div>
            <span className="chip chip-red font-mono ml-auto">
              {demoResult.events_fired} events / {demoResult.leads_touched} leads
            </span>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-2 max-h-[220px] overflow-y-auto">
            {demoResult.timeline.map((t, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                className="surface bg-white p-2 text-xs flex items-center gap-2"
              >
                <span
                  className="chip"
                  style={{
                    color: t.event === "replied" ? "#10B981" : t.event === "bounced" ? "#DC2626" : "#0F172A",
                    borderColor: t.event === "replied" ? "rgba(16,185,129,.4)" : t.event === "bounced" ? "rgba(220,38,38,.4)" : "rgba(15,23,42,.3)",
                  }}
                >
                  {t.event}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-[#0A0A0A] truncate">{t.lead}</div>
                  <div className="font-mono text-[#6B6B66]">stage: {t.stage} · score: {t.score}{t.suppressed ? " · suppressed" : ""}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {METRICS.map((m, i) => {
          const val = data.totals[m.key] || 0;
          return (
            <motion.div
              key={m.key}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="surface surface-hover p-5"
              data-testid={`metric-${m.key}`}
            >
              <div className="flex items-start justify-between">
                <m.icon size={22} weight="duotone" style={{ color: m.color }} />
                <ArrowUpRight size={14} className="text-[#999995]" />
              </div>
              <div className="mt-6">
                <div className="mono-accent" style={{ color: m.color }}>{m.label}</div>
                <div className="font-mono text-4xl font-bold mt-1 text-[#0A0A0A]">{val.toLocaleString()}</div>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Main charts grid */}
      <div className="grid lg:grid-cols-3 gap-4">
        {/* Timeseries */}
        <div className="surface p-6 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="mono-accent">/// outreach.throughput · 14d</div>
              <div className="font-display font-bold text-lg mt-0.5">Campaign Performance</div>
            </div>
            <div className="flex gap-3 text-xs font-mono">
              <span className="flex items-center gap-1.5"><span className="w-2 h-0.5 bg-[#DC2626]" /> sent</span>
              <span className="flex items-center gap-1.5"><span className="w-2 h-0.5 bg-[#0F172A]" /> opened</span>
              <span className="flex items-center gap-1.5"><span className="w-2 h-0.5 bg-[#10B981]" /> replied</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={data.timeseries} margin={{ top: 10, right: 10, bottom: 0, left: -20 }}>
              <defs>
                <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#DC2626" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#DC2626" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="g2" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0F172A" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#0F172A" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#E5E5DC" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" stroke="#999995" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="#999995" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #D6D3C8", borderRadius: 6 }} labelStyle={{ color: "#6B6B66", fontFamily: "JetBrains Mono" }} />
              <Area type="monotone" dataKey="sent" stroke="#DC2626" strokeWidth={2} fill="url(#g1)" />
              <Area type="monotone" dataKey="opened" stroke="#0F172A" strokeWidth={2} fill="url(#g2)" />
              <Line type="monotone" dataKey="replied" stroke="#10B981" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Channel Split */}
        <div className="surface p-6 flex flex-col">
          <div className="mono-accent">/// channel.split</div>
          <div className="font-display font-bold text-lg mt-0.5">Messaging Mix</div>

          <div className="flex-1 flex items-center justify-center min-h-[200px]">
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={data.channel_split} dataKey="value" nameKey="channel" cx="50%" cy="50%" innerRadius={50} outerRadius={78} strokeWidth={0}>
                  {data.channel_split.map((_, idx) => (
                    <Cell key={idx} fill={CHANNEL_COLORS[idx]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #D6D3C8", borderRadius: 6 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs font-mono">
            {data.channel_split.map((c, i) => (
              <div key={c.channel} className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-sm" style={{ background: CHANNEL_COLORS[i] }} />
                <span className="text-[#6B6B66] uppercase">{c.channel}</span>
                <span className="text-[#0A0A0A] ml-auto">{c.value}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Pipeline + rates + Activity */}
      <div className="grid lg:grid-cols-3 gap-4">
        <div className="surface p-6">
          <div className="mono-accent">/// rates</div>
          <div className="font-display font-bold text-lg mt-0.5 mb-4">Performance Index</div>
          <div className="space-y-5">
            <RateBar label="OPEN RATE" value={parseFloat(openRate)} color="#DC2626" />
            <RateBar label="REPLY RATE" value={parseFloat(replyRate)} color="#0F172A" />
            <div className="flex items-center justify-between pt-3 border-t border-[#D6D3C8]">
              <div>
                <div className="mono-accent">total.leads</div>
                <div className="font-mono text-2xl font-bold text-[#0A0A0A] mt-1">{data.leads_total}</div>
              </div>
              <Users size={36} weight="duotone" className="text-[#DC2626]/40" />
            </div>
          </div>
        </div>

        <div className="surface p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="mono-accent">/// pipeline</div>
              <div className="font-display font-bold text-lg mt-0.5">Lead Funnel</div>
            </div>
            <TrendUp size={18} className="text-[#10B981]" />
          </div>
          <div className="space-y-2">
            {Object.entries(data.pipeline).map(([stage, count]) => {
              const max = Math.max(...Object.values(data.pipeline), 1);
              const pct = (count / max) * 100;
              return (
                <div key={stage}>
                  <div className="flex justify-between text-xs font-mono mb-1">
                    <span className="uppercase text-[#6B6B66]">{stage}</span>
                    <span className="text-[#0A0A0A]">{count}</span>
                  </div>
                  <div className="h-1.5 bg-[#F0F0EA] rounded-sm overflow-hidden">
                    <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.6 }} className="h-full bg-gradient-to-r from-[#DC2626] to-[#0F172A]" />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Activity */}
        <div className="surface p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="mono-accent">/// live.feed</div>
              <div className="font-display font-bold text-lg mt-0.5">Activity Stream</div>
            </div>
            <Lightning size={18} className="text-[#F59E0B]" />
          </div>
          <div className="space-y-3 max-h-[280px] overflow-y-auto pr-1">
            {activity.slice(0, 10).map((a) => (
              <div key={a.id} className="flex items-start gap-3 text-sm">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-[#DC2626]" />
                <div className="flex-1 min-w-0">
                  <div className="text-[#1a1a1a] truncate">{a.title}</div>
                  <div className="mono-accent text-[#999995] mt-0.5">{a.kind}</div>
                </div>
              </div>
            ))}
            {activity.length === 0 && (
              <div className="text-[#999995] text-sm italic">No activity yet</div>
            )}
          </div>
        </div>
      </div>

      {/* Top countries */}
      <div className="surface p-6">
        <div className="mono-accent">/// global.reach</div>
        <div className="font-display font-bold text-lg mt-0.5 mb-4">Territories</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data.top_countries} margin={{ top: 10, right: 10, bottom: 0, left: -20 }}>
            <CartesianGrid stroke="#E5E5DC" vertical={false} />
            <XAxis dataKey="country" stroke="#999995" fontSize={11} tickLine={false} />
            <YAxis stroke="#999995" fontSize={11} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #D6D3C8", borderRadius: 6 }} />
            <Bar dataKey="leads" fill="#DC2626" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RateBar({ label, value, color }) {
  return (
    <div>
      <div className="flex justify-between items-baseline mb-1.5">
        <span className="mono-accent" style={{ color }}>{label}</span>
        <span className="font-mono text-2xl font-bold text-[#0A0A0A]">{value.toFixed(1)}<span className="text-[#999995] text-sm">%</span></span>
      </div>
      <div className="h-2 bg-[#F0F0EA] rounded-sm overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(value, 100)}%` }}
          transition={{ duration: 0.8 }}
          className="h-full"
          style={{ background: color, boxShadow: `0 0 10px ${color}` }}
        />
      </div>
    </div>
  );
}
