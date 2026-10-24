import { Fire, Snowflake, Thermometer } from "@phosphor-icons/react";
import { TIER_LABEL, heatTitle } from "@/lib/heat";

const STYLE = {
  hot: { cls: "chip chip-hot", Icon: Fire },
  warm: { cls: "chip chip-warm", Icon: Thermometer },
  cold: { cls: "chip chip-cold", Icon: Snowflake },
};

// The heat of a lead: tier, figure and a bar of how much real information is known. Hover or focus explains it.
export default function HeatBadge({ heat, compact = false }) {
  if (!heat) return <span className="chip" data-testid="heat-none">no heat</span>;
  const { cls, Icon } = STYLE[heat.tier];
  return (
    <span className="inline-flex items-center gap-2" title={heatTitle(heat)} aria-label={heatTitle(heat)} data-testid="heat-badge" data-tier={heat.tier}>
      {heat.top && <span className="chip chip-top" data-testid="heat-top">TOP</span>}
      <span className={cls}><Icon size={12} weight="fill" aria-hidden="true" /> {TIER_LABEL[heat.tier]} {heat.value}</span>
      {!compact && (
        <span className="inline-flex items-center gap-1" data-testid="heat-info">
          <span className="w-12 h-1.5 rounded bg-[#DDE4F1] overflow-hidden" aria-hidden="true"><span className="block h-full bg-gradient-to-r from-indigo-500 to-cyan-400" style={{ width: `${heat.info_pct}%` }} /></span>
          <span className="font-mono text-[10px] text-[#595955]">{heat.known.length}/{heat.known.length + heat.missing.length}</span>
        </span>
      )}
    </span>
  );
}
