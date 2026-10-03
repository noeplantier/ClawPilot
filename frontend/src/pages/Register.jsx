import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { Lightning, ArrowRight } from "@phosphor-icons/react";
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
    <div className="min-h-screen flex items-center justify-center bg-[#EDEBE0] grid-bg px-6 py-12 relative">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md surface p-10 relative z-10"
      >
        <Link to="/" className="flex items-center gap-2 mb-8" data-testid="brand-logo">
          <Lightning size={22} weight="fill" className="text-[#DC2626]" />
          <span className="font-display font-black tracking-tight text-xl">OutreachOS</span>
        </Link>

        <div className="mono-accent mb-3">// new.operator · init</div>
        <h1 className="text-3xl font-black tracking-tighter">Forge your command center</h1>
        <p className="text-[#6B6B66] mt-2">Provision an organization and deploy your first agents.</p>

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

        <p className="mt-6 text-sm text-[#6B6B66]">
          Existing operator?{" "}
          <Link to="/login" className="text-[#DC2626] hover:underline" data-testid="goto-login-link">
            Sign in →
          </Link>
        </p>
        <Footer className="mt-8 !border-0 !bg-transparent !px-0" />
      </motion.div>
    </div>
  );
}
