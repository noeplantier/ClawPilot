import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { ArrowRight } from "@phosphor-icons/react";
import Logo from "@/components/Logo";
import Footer from "@/components/Footer";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: "",
    organization_name: "",
    email: "",
    password: "",
  });
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
    <div className="min-h-screen flex items-center justify-center grid-bg grain px-6 py-12 relative overflow-hidden">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md surface p-10 relative z-10"
      >
        <Link to="/" className="inline-flex mb-8" data-testid="brand-logo" aria-label="Plantiers - OutreachOS">
          <Logo />
        </Link>

        <div className="mono-accent mb-3">// new.operator · init</div>
        <h1 className="text-3xl font-extrabold tracking-tighter">Forge your <span className="gradient-word">command center</span></h1>
        <p className="text-soft mt-2">Provision an organization and deploy your first agents.</p>

        <form onSubmit={submit} className="mt-8 space-y-4" data-testid="register-form">
          <div>
            <label className="mono-accent block mb-2">operator.name</label>
            <input required value={form.full_name} onChange={update("full_name")} className="neo-input" placeholder="Alex Rivera" data-testid="register-name-input" />
          </div>
          <div>
            <label className="mono-accent block mb-2">organization</label>
            <input required value={form.organization_name} onChange={update("organization_name")} className="neo-input" placeholder="Nova Labs" data-testid="register-org-input" />
          </div>
          <div>
            <label className="mono-accent block mb-2">email</label>
            <input type="email" required value={form.email} onChange={update("email")} className="neo-input font-mono" placeholder="alex@nova.io" data-testid="register-email-input" />
          </div>
          <div>
            <label className="mono-accent block mb-2">password</label>
            <input type="password" required value={form.password} onChange={update("password")} className="neo-input font-mono" placeholder="min 6 chars" minLength={6} data-testid="register-password-input" />
          </div>

          <button type="submit" disabled={loading} className="btn-primary w-full justify-center mt-4" data-testid="register-submit-button">
            {loading ? "PROVISIONING..." : "INITIALIZE COMMAND CENTER"} <ArrowRight size={16} weight="bold" />
          </button>
        </form>

        <p className="mt-6 text-sm text-soft">
          Existing operator?{" "}
          <Link to="/login" className="text-brand-lilac underline" data-testid="goto-login-link">
            Sign in →
          </Link>
        </p>
        <Footer className="mt-8 !border-0 !bg-transparent !px-0" />
      </motion.div>
    </div>
  );
}
