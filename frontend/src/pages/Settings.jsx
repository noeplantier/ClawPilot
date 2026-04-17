import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { CheckCircle, XCircle, Envelope, WhatsappLogo, Sparkle, Shield, Key } from "@phosphor-icons/react";

export default function Settings() {
  const { user, org } = useAuth();
  const [integrations, setIntegrations] = useState(null);

  useEffect(() => {
    api.get("/settings/integrations").then((r) => setIntegrations(r.data));
  }, []);

  return (
    <div className="p-6 md:p-10 max-w-4xl space-y-8">
      <div>
        <div className="mono-accent">// control.panel</div>
        <h1 className="text-4xl font-black tracking-tighter">Settings</h1>
        <p className="text-[#8B949E] mt-1">Organization profile and integration status.</p>
      </div>

      <section className="surface p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Shield size={18} className="text-[#00E5FF]" />
          <h2 className="font-display text-xl font-bold">Profile</h2>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <Row label="operator.name" value={user?.full_name} />
          <Row label="email" value={user?.email} mono />
          <Row label="role" value={user?.role} mono />
          <Row label="organization" value={org?.name} />
          <Row label="plan" value={org?.plan} mono />
          <Row label="org.id" value={org?.id} mono truncate />
        </div>
      </section>

      <section className="surface p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Key size={18} className="text-[#BF55EC]" />
          <h2 className="font-display text-xl font-bold">Integrations</h2>
        </div>

        <IntegrationRow
          icon={Sparkle}
          name="Gemini 3 Flash (AI)"
          description="Multi-language AI outreach message generation via Emergent universal LLM key."
          status={true}
          statusLabel="ACTIVE"
        />
        <IntegrationRow
          icon={Envelope}
          name="SendGrid Email"
          description="Transactional email sending with open & click tracking."
          status={integrations?.sendgrid_configured}
          statusLabel={integrations?.sendgrid_configured ? "ACTIVE" : "NEEDS VERIFIED SENDER"}
          details={[
            ["api.key", integrations ? "••••" + "configured" : "—"],
            ["from.email", integrations?.sendgrid_from_email || "not set"],
          ]}
        />
        <IntegrationRow
          icon={WhatsappLogo}
          name="Twilio WhatsApp"
          description="Outbound WhatsApp via Twilio. Falls back to MOCK dispatch if not fully configured."
          status={integrations?.twilio_account_sid_configured}
          statusLabel={integrations?.twilio_account_sid_configured ? "ACTIVE" : "NEEDS ACCOUNT SID"}
          details={[
            ["from.number", integrations?.twilio_whatsapp_from || "—"],
            ["note", "Your SK key is an API Key SID. For direct REST you need an Account SID (starts with AC)."],
          ]}
        />
      </section>

      <p className="mono-accent text-[#4B5563]">
        // To go live with real email/whatsapp sending, provide a verified SendGrid sender and Twilio Account SID (AC...) in backend/.env.
      </p>
    </div>
  );
}

function Row({ label, value, mono, truncate }) {
  return (
    <div>
      <div className="mono-accent">{label}</div>
      <div className={`mt-1 ${mono ? "font-mono text-sm" : "font-display font-semibold"} ${truncate ? "truncate" : ""}`}>
        {value || "—"}
      </div>
    </div>
  );
}

function IntegrationRow({ icon: Icon, name, description, status, statusLabel, details = [] }) {
  return (
    <div className="surface p-5 bg-[#0c0c0c]">
      <div className="flex items-start gap-4">
        <Icon size={24} weight="duotone" className="text-[#00E5FF] mt-1" />
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-display font-semibold">{name}</h3>
            {status
              ? <span className="chip chip-success"><CheckCircle size={10} weight="fill" /> {statusLabel}</span>
              : <span className="chip chip-warn"><XCircle size={10} weight="fill" /> {statusLabel}</span>
            }
          </div>
          <p className="text-sm text-[#8B949E] mt-1">{description}</p>
          {details.length > 0 && (
            <div className="mt-3 grid md:grid-cols-2 gap-2 text-xs">
              {details.map(([k, v]) => (
                <div key={k} className="flex gap-2 font-mono">
                  <span className="text-[#4B5563]">{k}:</span>
                  <span className="text-[#e6edf3] truncate">{v}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
