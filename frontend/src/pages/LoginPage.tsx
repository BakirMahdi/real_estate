import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Building2, LogIn, UserPlus } from "lucide-react";
import { api, setAuthToken } from "../api/client";

export function LoginPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isLogin) {
        const response = await api.login(username, password);
        setAuthToken(response.access_token);
        localStorage.setItem("user_role", response.role);
        navigate("/dashboard");
      } else {
        await api.register(username, password);
        // Auto-login after registration
        const response = await api.login(username, password);
        setAuthToken(response.access_token);
        localStorage.setItem("user_role", response.role);
        navigate("/dashboard");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <Link
            to="/"
            className="inline-flex items-center justify-center gap-3"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 shadow-glow">
              <Building2 className="h-6 w-6 text-white" />
            </div>
            <div className="text-left">
              <p className="font-display text-2xl font-semibold tracking-tight text-slate-900">
                Rews
              </p>
              <p className="text-sm text-slate-500">Immobilier Tunisie</p>
            </div>
          </Link>
        </div>

        <div className="glass rounded-2xl p-8">
          <div className="mb-6">
            <h1 className="font-display text-2xl font-semibold tracking-tight text-slate-900">
              {isLogin ? "Connexion" : "Créer un compte"}
            </h1>
            <p className="mt-2 text-sm text-slate-500">
              {isLogin
                ? "Connectez-vous pour accéder au dashboard"
                : "Créez un compte pour commencer"}
            </p>
          </div>

          {error && (
            <div className="mb-4 rounded-lg bg-red-500/10 border border-red-500/20 p-3">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="username"
                className="mb-2 block text-sm font-medium text-slate-700"
              >
                Nom d'utilisateur
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white px-4 py-3 text-slate-900 placeholder-slate-400 transition focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                placeholder="votre_nom"
                required
                minLength={3}
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-2 block text-sm font-medium text-slate-700"
              >
                Mot de passe
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white px-4 py-3 text-slate-900 placeholder-slate-400 transition focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                placeholder="••••••••"
                required
                minLength={6}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2"
            >
              {loading ? (
                "Chargement..."
              ) : isLogin ? (
                <>
                  <LogIn className="h-4 w-4" />
                  Se connecter
                </>
              ) : (
                <>
                  <UserPlus className="h-4 w-4" />
                  Créer un compte
                </>
              )}
            </button>
          </form>

          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={() => {
                setIsLogin(!isLogin);
                setError(null);
              }}
              className="text-sm text-slate-500 transition hover:text-slate-900"
            >
              {isLogin
                ? "Pas encore de compte ? Créer un compte"
                : "Déjà un compte ? Se connecter"}
            </button>
          </div>
        </div>

        <div className="mt-6 text-center">
          <Link
            to="/"
            className="text-sm text-slate-500 transition hover:text-slate-900"
          >
            ← Retour à l'accueil
          </Link>
        </div>
      </div>
    </div>
  );
}
