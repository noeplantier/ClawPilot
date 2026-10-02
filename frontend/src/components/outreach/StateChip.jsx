import { STATE_META } from "@/lib/outreachFormat";

// Glyph + word + colour: the state is never conveyed by colour alone.
export default function StateChip({ state }) {
  const meta = STATE_META[state] || { label: state, chip: "chip", glyph: "?", hint: "" };
  return (
    <span className={`chip ${meta.chip}`} title={meta.hint} data-testid={`state-${state}`}>
      <span aria-hidden="true" className="mr-1">
        {meta.glyph}
      </span>
      {meta.label}
    </span>
  );
}
