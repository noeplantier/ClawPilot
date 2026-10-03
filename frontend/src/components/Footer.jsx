import { Link } from "react-router-dom";
import { PUBLISHER } from "@/config/legal";

export default function Footer({ className = "" }) {
  return (
    <footer className={`border-t border-[#D6D3C8] bg-white/70 px-6 py-4 text-xs text-[#6B6B66] ${className}`} data-testid="app-footer">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <span>© {PUBLISHER.company}</span>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-4 gap-y-1">
          <a href={PUBLISHER.website} className="underline-offset-2 hover:underline" rel="noopener" data-testid="footer-site">plantiers.com</a>
          <Link to="/legal" className="underline-offset-2 hover:underline" data-testid="footer-legal">Mentions légales</Link>
          <Link to="/privacy" className="underline-offset-2 hover:underline" data-testid="footer-privacy">Politique de confidentialité</Link>
          <Link to="/terms" className="underline-offset-2 hover:underline" data-testid="footer-terms">Conditions d&apos;utilisation</Link>
        </nav>
      </div>
    </footer>
  );
}
