import { useEffect, useRef, useState } from "react";
import { insertToken } from "@/lib/journeyFormat";
import { siteState } from "@/lib/launchFormat";

const FIELD = "neo-input w-full";

// The message frame: edited once, rendered per establishment by the server, a few real examples next to it.
// The footer (sender identity, origin of the data, unsubscribe link) is added by the server and cannot be edited here.
export default function TemplateEditor({ template, examples, decide, busy, onSave }) {
  const [subject, setSubject] = useState(template.subject);
  const [body, setBody] = useState(template.body);
  const bodyRef = useRef(null);
  // A new saved version (or an edit from elsewhere) replaces what is typed only when nothing unsaved is being typed.
  const savedKey = `${template.version}:${template.content_hash}`;
  const lastKey = useRef(savedKey);
  useEffect(() => {
    if (lastKey.current !== savedKey) {
      lastKey.current = savedKey;
      setSubject(template.subject);
      setBody(template.body);
    }
  }, [savedKey, template.subject, template.body]);

  const dirty = subject !== template.subject || body !== template.body;
  const insert = (name) => {
    const el = bodyRef.current;
    const out = insertToken(body, el ? el.selectionStart : undefined, el ? el.selectionEnd : undefined, `{{${name}}}`);
    setBody(out.text);
    window.requestAnimationFrame(() => { if (el) { el.focus(); el.setSelectionRange(out.caret, out.caret); } });
  };

  return (
    <section aria-label="Message" className="rounded-2xl border border-border bg-card p-4 space-y-3" data-testid="journey-template">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-lg font-bold">Message <span className="text-sm font-normal text-soft">· version {template.version}</span></h2>
        {dirty && <span className="chip chip-warn" data-testid="template-dirty">Modifications non enregistrées</span>}
      </div>
      <label className="block text-sm">
        <span className="text-soft">Objet</span>
        <input className={FIELD} value={subject} onChange={(e) => setSubject(e.target.value)} disabled={!decide} maxLength={200} data-testid="template-subject" />
      </label>
      <label className="block text-sm">
        <span className="text-soft">Corps du message</span>
        <textarea ref={bodyRef} className={`${FIELD} min-h-[11rem] font-mono text-[13px]`} value={body} onChange={(e) => setBody(e.target.value)} disabled={!decide} maxLength={6000} data-testid="template-body" />
      </label>
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Champs de fusion">
        <span className="text-xs text-faint">Insérer :</span>
        {template.placeholders.map((name) => (
          <button key={name} type="button" className="chip chip-ink hover:bg-white/10" onClick={() => insert(name)} disabled={!decide} data-testid={`insert-${name}`}>{`{{${name}}}`}</button>
        ))}
      </div>
      {template.problems.length > 0 && (
        <ul role="alert" className="text-sm text-red-300 list-disc pl-5" data-testid="template-problems">
          {template.problems.map((p) => <li key={p.code}>{p.label}</li>)}
        </ul>
      )}
      <p className="text-xs text-faint" data-testid="template-footer-note">{template.footer_note}</p>
      {decide && (
        <button className="btn-ink" onClick={() => onSave(subject, body)} disabled={!dirty || busy === "template"} data-testid="template-save">
          {busy === "template" ? "ENREGISTREMENT…" : "ENREGISTRER LE MESSAGE"}
        </button>
      )}

      <div className="border-t border-border pt-3">
        <h3 className="text-sm font-semibold">Exemples rendus avec de vrais établissements de la zone</h3>
        {examples.length === 0 ? (
          <p className="mt-1 text-sm text-soft" data-testid="examples-none">Aucun établissement ne peut encore recevoir ce message : pas d&apos;exemple à inventer.</p>
        ) : (
          <ul className="mt-2 grid gap-3 md:grid-cols-3" data-testid="examples">
            {examples.map((ex) => {
              const site = siteState(ex.site_state);
              return (
                <li key={`${ex.name}-${ex.email}`} className="rounded-xl border border-border bg-black/20 p-3 text-xs space-y-1.5" data-testid="example">
                  <div className="flex items-center justify-between gap-2"><b className="truncate">{ex.name}</b><span className={`chip ${site.chip}`}>{site.label}</span></div>
                  <div className="font-medium">{ex.subject}</div>
                  <pre className="whitespace-pre-wrap font-sans text-soft">{ex.body}</pre>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
