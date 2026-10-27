/* global AbortController */
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { CircleNotch, Fire, MapPin, X } from "@phosphor-icons/react";
import {
  MIN_CHARS, addressUrl, communesUrl, countsText, fold, hottest, isPostcode, parseAddress, parseCommunes, suggest,
} from "@/lib/cityComplete";

// The town search of the map: a combobox that answers as you type, from the official French communes list, and says next to each
// town how many of YOUR leads are there (counted by the server). It opens on focus and on click, every time; it narrows at once
// while the next answer is on its way; answers are kept per text, so going back is instant. Only the typed text leaves the browser.

const DEBOUNCE_MS = 120;
const LIST = "bg-card border border-white/10 ring-1 ring-indigo-500/10 shadow-[0_14px_44px_-12px_rgba(30,41,90,0.5)]"; // opaque: the panel below must not show through

// The communes API first (official, ranked by population); the address API when it fails or knows nothing of the text.
// Throws only when no service could answer at all: an empty list is a real answer ("no such town").
export async function lookup(query, signal) {
  const stopped = (e) => { if (signal && signal.aborted) throw e; };
  let answered = false;
  try {
    const res = await fetch(communesUrl(query), { signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const items = parseCommunes(await res.json());
    answered = true;
    if (items.length || isPostcode(query)) return items;
  } catch (e) {
    stopped(e);
  }
  try {
    const res = await fetch(addressUrl(query), { signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return parseAddress(await res.json());
  } catch (e) {
    stopped(e);
    if (answered) return []; // the first service did answer: "no such town" is its answer, the fallback only failed to add to it
    throw e;
  }
}

function Counts({ counts }) {
  const text = countsText(counts);
  if (!text) return null;
  if (counts.total === 0) return <span className="text-[11px] italic text-faint shrink-0" data-testid="city-counts" data-tier="none">{text}</span>;
  const tier = counts.hot > 0 ? "hot" : counts.warm > 0 ? "warm" : "cold";
  return (
    <span className={`chip chip-${tier} shrink-0`} data-testid="city-counts" data-tier={tier} title={`${counts.hot} hot, ${counts.warm} warm, ${counts.cold} cold`}>
      {counts.hot > 0 && <Fire size={12} weight="fill" aria-hidden="true" />} {text}
    </span>
  );
}

export default function CityBox({ stats, positions, onPick, className = "" }) {
  const listId = useId();
  const box = useRef(null);
  const input = useRef(null);
  const cache = useRef(new Map()); // folded text -> suggestions, for the life of the page
  const queryRef = useRef("");
  const [text, setText] = useState("");
  const [picked, setPicked] = useState(null); // the town chosen last: the box keeps showing it, and a new focus lists it again
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [remote, setRemote] = useState({ for: "", items: [] });
  const [phase, setPhase] = useState("idle"); // idle | loading | error
  const [note, setNote] = useState(null);

  const query = picked ? picked.name : text;
  const folded = fold(query);
  queryRef.current = query;

  useEffect(() => {
    if (!open || folded.length < MIN_CHARS) { setPhase("idle"); return undefined; }
    const hit = cache.current.get(folded);
    if (hit) { setRemote({ for: folded, items: hit }); setPhase("idle"); return undefined; }
    const ctl = new AbortController();
    setPhase("loading");
    const timer = setTimeout(() => {
      lookup(queryRef.current, ctl.signal).then(
        (items) => { cache.current.set(folded, items); setRemote({ for: folded, items }); setPhase("idle"); },
        () => { if (!ctl.signal.aborted) setPhase("error"); },
      );
    }, DEBOUNCE_MS);
    return () => { clearTimeout(timer); ctl.abort(); };
  }, [folded, open]);

  // Click or touch outside closes the list; the next click on the box opens it again.
  useEffect(() => {
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("touchstart", away);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("touchstart", away); };
  }, []);

  const items = useMemo(
    () => (folded.length < MIN_CHARS ? hottest(stats, 6, positions) : suggest(query, { remote: remote.items, remoteFor: remote.for, stats, positions })),
    [folded, query, remote, stats, positions],
  );
  const searching = folded.length >= MIN_CHARS;

  const choose = useCallback(async (entry) => {
    setPicked(entry);
    setText(entry.label);
    setOpen(false);
    setActive(-1);
    setNote(null);
    let at = entry;
    if (entry.lat === null || entry.lon === null) { // a town known only from the leads and with no position yet: look it up once
      try {
        const found = (await lookup(entry.name))[0];
        if (found) at = { ...entry, lat: found.lat, lon: found.lon, population: found.population };
      } catch { /* said below */ }
    }
    if (at.lat === null || at.lon === null) { setNote(`${entry.name}: no position found. Type the town and pick it from the list.`); return; }
    onPick(at);
  }, [onPick]);

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) { setOpen(true); return; }
      if (items.length) setActive((i) => (e.key === "ArrowDown" ? (i + 1) % items.length : (i - 1 + items.length) % items.length));
    } else if (e.key === "Enter") {
      if (open && items.length) { e.preventDefault(); choose(items[active >= 0 ? active : 0]); }
    } else if (e.key === "Escape" && open) {
      e.preventDefault();
      setOpen(false);
    }
  };

  const edit = (value) => { setPicked(null); setText(value); setOpen(true); setActive(-1); setNote(null); };
  const clear = () => { edit(""); if (input.current) input.current.focus(); };
  const empty = searching && phase !== "loading" && items.length === 0;
  const header = searching ? null : items.length ? "Your hottest towns" : "Type a town or a postcode";

  return (
    <div ref={box} className={`relative ${className}`} data-testid="city-box">
      <MapPin size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint pointer-events-none" aria-hidden="true" />
      <input
        ref={input} className="neo-input w-full !pl-9 !pr-9" placeholder="Go to a town or a postcode… (e.g. Lyon)" value={text} autoComplete="off" spellCheck="false"
        role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list" aria-label="Go to a town"
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        onChange={(e) => edit(e.target.value)} onFocus={(e) => { setOpen(true); e.target.select(); }} onClick={() => setOpen(true)} onKeyDown={onKeyDown}
        data-testid="map-goto"
      />
      {phase === "loading" && <CircleNotch size={16} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-brand-lilac" aria-hidden="true" data-testid="city-loading" />}
      {phase !== "loading" && text && (
        <button type="button" className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-full hover:bg-white/10" onClick={clear} aria-label="Clear the town" data-testid="city-clear">
          <X size={14} />
        </button>
      )}
      {open && (
        <ul id={listId} role="listbox" aria-label="Towns" className={`absolute left-0 right-0 mt-1 z-20 max-h-72 overflow-auto rounded-lg py-1 ${LIST}`} data-testid="map-cities">
          {header && <li role="presentation" className="px-3 pt-1 pb-0.5 mono-accent" data-testid="city-header">{header}</li>}
          {items.map((e, i) => (
            <li key={e.id} role="presentation">
              <button
                type="button" role="option" id={`${listId}-${i}`} aria-selected={i === active} tabIndex={-1}
                className={`w-full text-left px-3 py-2 text-sm flex gap-2 items-center ${i === active ? "bg-white/10" : "hover:bg-white/10"}`}
                onMouseDown={(ev) => ev.preventDefault()} onMouseEnter={() => setActive(i)} onClick={() => choose(e)} data-testid={`map-city-${i}`}
              >
                <MapPin size={14} className="shrink-0 text-brand-lilac" aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="font-semibold block truncate">{e.label}</span>
                  {e.detail && <span className="block text-[11px] text-faint truncate" data-testid="city-detail">{e.detail}</span>}
                </span>
                <Counts counts={e.counts} />
              </button>
            </li>
          ))}
          {empty && phase !== "error" && (
            <li role="presentation" className="px-3 py-2 text-sm text-soft" data-testid="city-none">
              {/^\d+$/.test(folded) && folded.length < 5 ? "Type the 5 digits of the postcode." : `No town matches “${query.trim()}”.`}
            </li>
          )}
          {phase === "error" && (
            <li role="presentation" className="px-3 py-2 text-xs text-amber-300" data-testid="city-error">
              The official town lists did not answer{items.length ? ": showing only the towns of your leads." : ". Check your connection and type again."}
            </li>
          )}
        </ul>
      )}
      <p className="sr-only" role="status" aria-live="polite">{open && searching && phase !== "loading" ? `${items.length} town${items.length === 1 ? "" : "s"} found` : ""}</p>
      {note && <p className="text-xs text-amber-300 mt-1" role="status" data-testid="city-note">{note}</p>}
    </div>
  );
}
