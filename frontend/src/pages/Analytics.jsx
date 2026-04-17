import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, RadialBarChart, RadialBar, Legend,
} from "recharts";

export default function Analytics() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/analytics/overview").then((r) => setData(r.data)); }, []);

  if (!data) return <div className="p-10 text-[#8B949E] font-mono">loading telemetry...</div>;

  const { totals, timeseries, pipeline, top_countries } = data;

  const funnel = [
    { name: "Sent",      value: totals.sent,      fill: "#00E5FF" },
    { name: "Opened",    value: totals.opened,    fill: "#BF55EC" },
    { name: "Replied",   value: totals.replied,   fill: "#2962FF" },
    { name: "Converted", value: totals.converted, fill: "#10B981" },
  ];

  return (
    <div className="p-6 md:p-10 space-y-6">
      <div>
        <div className="mono-accent">// deep.analytics</div>
        <h1 className="text-4xl font-black tracking-tighter">Analytics</h1>
        <p className="text-[#8B949E] mt-1">Cross-channel performance breakdown.</p>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="surface p-6">
          <div className="mono-accent">/// funnel</div>
          <div className="font-display font-bold text-lg mt-0.5 mb-4">Conversion Funnel</div>
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={funnel} layout="vertical" margin={{ left: 20, right: 20 }}>
                <CartesianGrid stroke="#141414" horizontal={false} />
                <XAxis type="number" stroke="#4B5563" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis dataKey="name" type="category" stroke="#e6edf3" fontSize={12} tickLine={false} axisLine={false} width={80} />
                <Tooltip contentStyle={{ background: "#0A0A0A", border: "1px solid #262626", borderRadius: 6 }} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="surface p-6">
          <div className="mono-accent">/// throughput</div>
          <div className="font-display font-bold text-lg mt-0.5 mb-4">14-day Velocity</div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={timeseries} margin={{ top: 10, right: 10, bottom: 0, left: -20 }}>
              <defs>
                <linearGradient id="an1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#BF55EC" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#BF55EC" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#141414" vertical={false} />
              <XAxis dataKey="date" stroke="#4B5563" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="#4B5563" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#0A0A0A", border: "1px solid #262626", borderRadius: 6 }} />
              <Area type="monotone" dataKey="replied" stroke="#BF55EC" fill="url(#an1)" strokeWidth={2} />
              <Line type="monotone" dataKey="opened" stroke="#00E5FF" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="surface p-6">
          <div className="mono-accent">/// pipeline.heatmap</div>
          <div className="font-display font-bold text-lg mt-0.5 mb-4">Pipeline Density</div>
          <div className="space-y-3">
            {Object.entries(pipeline).map(([stage, count]) => {
              const max = Math.max(...Object.values(pipeline), 1);
              const pct = (count / max) * 100;
              return (
                <div key={stage} className="flex items-center gap-3">
                  <div className="mono-accent w-24">{stage}</div>
                  <div className="flex-1 h-6 bg-[#141414] rounded-sm overflow-hidden relative">
                    <div className="h-full bg-gradient-to-r from-[#00E5FF] to-[#BF55EC]" style={{ width: `${pct}%` }} />
                    <div className="absolute inset-0 flex items-center justify-end pr-2 font-mono text-xs text-white">{count}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="surface p-6">
          <div className="mono-accent">/// territories</div>
          <div className="font-display font-bold text-lg mt-0.5 mb-4">Geographic Reach</div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={top_countries} margin={{ top: 10, right: 10, bottom: 0, left: -20 }}>
              <CartesianGrid stroke="#141414" vertical={false} />
              <XAxis dataKey="country" stroke="#4B5563" fontSize={11} />
              <YAxis stroke="#4B5563" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#0A0A0A", border: "1px solid #262626", borderRadius: 6 }} />
              <Bar dataKey="leads" fill="#BF55EC" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
