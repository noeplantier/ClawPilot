import { Link } from "react-router-dom";
import { useEffect } from "react";
import Footer from "@/components/Footer";
import { REVIEW_PENDING } from "@/config/legal";

export default function LegalLayout({ title, updated, children, testId }) {
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} | Plantiers - OutreachOS`;
    return () => { document.title = previous; };
  }, [title]);

  return (
    <div className="min-h-screen flex flex-col bg-white/[0.04] text-foreground">
      <header className="px-6 md:px-16 py-6 border-b border-border bg-card">
        <Link to="/" className="font-display font-black tracking-tight text-lg" data-testid="legal-home">
          Plantiers - OutreachOS
        </Link>
      </header>
      <main className="flex-1 px-6 md:px-16 py-10 max-w-3xl w-full mx-auto" data-testid={testId}>
        <div className="mono-accent">// legal</div>
        <h1 className="text-4xl font-black tracking-tighter mt-1">{title}</h1>
        <p className="text-sm text-soft mt-1">Dernière mise à jour : {updated}</p>
        {REVIEW_PENDING && (
          <p role="note" className="mt-4 text-sm text-amber-300 bg-amber-500/10 border border-amber-400/40 rounded-md p-3" data-testid="review-pending">
            Ce texte n&apos;a pas encore été validé par un conseil juridique. Il décrit le fonctionnement réel du service ; les
            points à compléter sont signalés.
          </p>
        )}
        <div className="mt-8 space-y-8 leading-relaxed [&_h2]:font-display [&_h2]:text-xl [&_h2]:font-bold [&_h2]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1 [&_a]:underline">
          {children}
        </div>
      </main>
      <Footer />
    </div>
  );
}
