import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { ArrowRight } from "@phosphor-icons/react";
import AuthShell from "@/components/AuthShell";

const FIELDS = [
  { key: "full_name", label: "operator.name", id: "register-name", testId: "register-name-input", autoComplete: "name", placeholder: "Alex Rivera" },
  { key: "organization_name", label: "organization", id: "register-org", testId: "register-org-input", autoComplete: "organization", placeholder: "Nova Labs" },
  { key: "email", label: "email", id: "register-email", testId: "register-email-input", autoComplete: "username", placeholder: "alex@nova.io", type: "email", mono: true },
  { key: "password", label: "password", id: "register-password", testId: "register-password-input", autoComplete: "new-password", placeholder: "min 6 chars", type: "password", mono: true, minLength: 6 },
];

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", organization_name: "", email: "", password: "" });
  const [loading, setLoading] = useState(false);
  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await register(form);
      toast.success("Command center initialized.");
      navigate("/app/dashboard");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell testId="register-page">
      <div className="mono-accent mb-3">// new.operator · init</div>
      <h1 className="text-3xl font-extrabold tracking-tighter">Forge your <span className="gradient-word">command center</span></h1>
      <p className="mt-2 text-soft">Create an organization, then qualify prospects and prepare drafts for a person to approve.</p>

      <form onSubmit={submit} className="mt-8 space-y-4" data-testid="register-form">
        {FIELDS.map((f) => (
          <div key={f.key}>
            <label className="mono-accent mb-2 block" htmlFor={f.id}>{f.label}</label>
            <input
              id={f.id}
              name={f.key}
              type={f.type || "text"}
              required
              minLength={f.minLength}
              value={form[f.key]}
              onChange={update(f.key)}
              className={`neo-input w-full ${f.mono ? "font-mono" : ""}`}
              placeholder={f.placeholder}
              autoComplete={f.autoComplete}
              data-testid={f.testId}
            />
          </div>
        ))}
        <button type="submit" disabled={loading} className="btn-primary mt-4 w-full justify-center" data-testid="register-submit-button">
          {loading ? "PROVISIONING..." : "INITIALIZE COMMAND CENTER"} <ArrowRight size={16} weight="bold" />
        </button>
      </form>

      <p className="mt-6 text-sm text-soft">
        Existing operator?{" "}
        <Link to="/login" className="text-brand-lilac underline" data-testid="goto-login-link">Sign in →</Link>
      </p>
    </AuthShell>
  );
}
