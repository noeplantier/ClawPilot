import logoMark from "@/assets/logo-mark.png";

// The Plantiers mark (ribbon "P" + leaf sprout), the one of plantiers.com. Fixed width/height keep the layout still while it loads.
export function LogoMark({ className = "h-9", decorative = false }) {
  return (
    <img
      src={logoMark}
      alt={decorative ? "" : "Plantiers"}
      aria-hidden={decorative ? "true" : undefined}
      width="200"
      height="280"
      decoding="async"
      className={`w-auto shrink-0 object-contain ${className}`}
      style={{ aspectRatio: "200 / 280" }}
    />
  );
}

// Lockup as on the site: mark, PLANTIERS, and a mono sub-line (here the product: OUTREACHOS).
export default function Logo({ product = "OUTREACHOS", markClass = "h-9", className = "" }) {
  return (
    <span className={`inline-flex items-center gap-3 ${className}`}>
      <LogoMark decorative className={markClass} />
      <span className="flex flex-col leading-none">
        <span className="text-lg font-extrabold tracking-tight text-white">PLANTIERS</span>
        <span className="mt-1 font-mono text-[9px] tracking-[0.25em] text-brand-lilac/80">{product}</span>
      </span>
    </span>
  );
}
