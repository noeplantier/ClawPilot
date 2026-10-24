import { useState } from "react";
import { CircleNotch, Plus, UserPlus } from "@phosphor-icons/react";
import { mapApi } from "@/lib/outreach";
import { describeApiError } from "@/lib/outreachFormat";
import { readPref, writePref } from "@/lib/uiPrefs";
import { ATTEST_PREF, ATTEST_TEXT, quickAddBody } from "@/lib/mapQuickAdd";

// The content of a map pin's popup: what the map published about the place, and the fastest way to make it a prospect.
// "Add to CRM" is the person's own decision for this one business (audited); "Add for review" leaves it to the review queue.
export default function PlacePopup({ place, canAdd, offReason, onAdded }) {
  const [attest, setAttest] = useState(() => readPref(ATTEST_PREF, false));
  const [readSite, setReadSite] = useState(true);
  const [busy, setBusy] = useState(null);
  const [out, setOut] = useState(null);
  const [error, setError] = useState(null);

  const changeAttest = (value) => {
    setAttest(value);
    writePref(ATTEST_PREF, value); // remembered on this browser; every request still carries it and is audited
  };

  const add = async (approve) => {
    setBusy(approve ? "crm" : "review");
    setError(null);
    try {
      const done = await mapApi.addPlace(quickAddBody(place, { approve, checkWebsite: readSite }));
      setOut(done);
      if (onAdded) onAdded(done, place, { siteAsked: readSite && Boolean(place.website) });
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(null);
    }
  };

  const address = [place.address, place.postcode, place.city].filter(Boolean).join(", ");
  const fact = (label, value) => (
    <div><b>{label}</b> {value || <i>not published</i>}</div>
  );

  return (
    <div className="w-[17rem] max-w-full text-xs space-y-2" data-testid="place-popup">
      <strong className="text-sm block leading-tight">{place.name}</strong>
      {fact("address", address)}
      {fact("phone", place.phone)}
      {fact("e-mail", place.email)}
      <div>
        <b>site</b>{" "}
        {place.website ? <a href={place.website} target="_blank" rel="noopener noreferrer" className="underline break-all">{place.website}</a> : <i>not published</i>}
      </div>
      <a href={place.source_url} target="_blank" rel="noopener noreferrer" className="underline block">source on OpenStreetMap</a>

      {out ? (
        <p className="rounded-lg border border-emerald-500/40 bg-emerald-50 p-2 font-semibold" role="status" data-testid="place-done">
          {out.in_crm ? "Added to your CRM." : "Added: it waits for review."}
        </p>
      ) : !canAdd ? (
        <p className="text-[#92400E]" data-testid="place-add-off">{offReason}</p>
      ) : (
        <div className="space-y-2 border-t border-[#D3DBEA] pt-2">
          {place.website && (
            <label className="flex items-start gap-2">
              <input type="checkbox" checked={readSite} onChange={(e) => setReadSite(e.target.checked)} className="mt-0.5" data-testid="place-read-site" />
              <span>Look for a public e-mail on its own website (robots.txt respected)</span>
            </label>
          )}
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={attest} onChange={(e) => changeAttest(e.target.checked)} className="mt-0.5" data-testid="place-attest" />
            <span>{ATTEST_TEXT}</span>
          </label>
          <div className="flex gap-2 flex-wrap">
            <button className="btn-primary !py-1.5 !px-3" disabled={!attest || busy !== null} onClick={() => add(true)} data-testid="place-add">
              {busy === "crm" ? <CircleNotch size={12} className="animate-spin" /> : <UserPlus size={12} weight="fill" />} ADD TO CRM
            </button>
            <button className="btn-ghost !py-1.5 !px-3" disabled={!attest || busy !== null} onClick={() => add(false)} data-testid="place-add-review">
              {busy === "review" ? <CircleNotch size={12} className="animate-spin" /> : <Plus size={12} />} FOR REVIEW
            </button>
          </div>
          {error && <p role="alert" className="text-[#991B1B]" data-testid="place-error">{error}</p>}
        </div>
      )}
    </div>
  );
}
