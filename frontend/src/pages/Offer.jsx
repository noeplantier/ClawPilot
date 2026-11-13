import OfferCard from "@/components/outreach/OfferCard";

// What you sell: the one offer the automatic drafts talk about.
export default function Offer() {
  return (
    <div className="p-6 md:p-10 max-w-4xl space-y-6" data-testid="offer-page">
      <div>
        <div className="eyebrow">control.offer</div>
        <h1 className="mt-3 text-4xl font-bold tracking-tight leading-[1.15]">Offer</h1>
        <p className="text-soft mt-1">Describe what you sell once. Every qualified prospect then gets a short draft about it, to review before anything is sent.</p>
      </div>
      <OfferCard />
    </div>
  );
}
