import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, Building2, LogIn, UserPlus } from "lucide-react";
import { api, setSession } from "../api/client";
import { useLang } from "../lib/i18n";

// Maps raw backend/network error messages to i18n keys so the friendly
// message follows the selected language.
function authErrorKey(err: unknown): string {
  const msg = err instanceof Error ? err.message : "";
  if (
    msg === "UNAUTHORIZED" ||
    msg.includes("Invalid email or password") ||
    msg.includes("Invalid username or password")
  ) {
    return "error.badCredentials";
  }
  if (msg.includes("already registered")) return "error.emailExists";
  if (msg.includes("valid email")) return "error.emailInvalid";
  if (msg.includes("Email not verified")) return "error.emailNotVerified";
  if (msg.includes("verification code")) return "error.codeInvalid";
  if (msg.includes("verification email")) return "error.emailSendFailed";
  if (msg.includes("Password must be at least")) return "error.passwordShort";
  if (msg.toLowerCase().includes("rate limit")) return "error.rateLimited";
  if (msg.includes("Request timeout")) return "error.timeout";
  if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) return "error.network";
  return "error.generic";
}

// Loads the Google Identity Services script once, resolving when ready.
function loadGoogleScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as { google?: unknown }).google) return resolve();
    const existing = document.getElementById("gis-script") as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("GIS load failed")));
      return;
    }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.id = "gis-script";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("GIS load failed"));
    document.head.appendChild(script);
  });
}

export function LoginPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // When set, we've sent a code to this address and are showing the
  // "enter your verification code" step instead of the login/register form.
  const [pendingEmail, setPendingEmail] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [googleClientId, setGoogleClientId] = useState<string | null>(null);
  const googleBtnRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { t } = useLang();

  // Google sign-in is only offered when the backend has a client id configured.
  useEffect(() => {
    api
      .getAuthConfig()
      .then((cfg) => setGoogleClientId(cfg.google_client_id || null))
      .catch(() => setGoogleClientId(null));
  }, []);

  useEffect(() => {
    if (!googleClientId || !googleBtnRef.current) return;
    let cancelled = false;
    loadGoogleScript()
      .then(() => {
        if (cancelled || !googleBtnRef.current) return;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const google = (window as any).google;
        google.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (resp: { credential: string }) => {
            try {
              const r = await api.googleLogin(resp.credential);
              setSession(r.role, r.username);
              navigate("/annonces");
            } catch {
              setError("error.google");
            }
          },
        });
        google.accounts.id.renderButton(googleBtnRef.current, {
          theme: "outline",
          size: "large",
          width: 320,
          text: "continue_with",
        });
      })
      .catch(() => setGoogleClientId(null));
    return () => {
      cancelled = true;
    };
  }, [googleClientId, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setLoading(true);

    try {
      if (isLogin) {
        const response = await api.login(email, password);
        setSession(response.role, response.username);
        navigate("/annonces");
      } else {
        // Register -> a code is emailed; move to the verification step
        // instead of logging in immediately.
        const response = await api.register(email, password);
        setPendingEmail(response.email);
        setCode("");
        setInfo("verify.sent");
      }
    } catch (err) {
      // Logging in to an account that never confirmed its email: send a fresh
      // code and drop the user into the verification step.
      if (isLogin && err instanceof Error && err.message.includes("Email not verified")) {
        try {
          await api.resendCode(email);
        } catch {
          /* ignore: we still want to show the code step */
        }
        setPendingEmail(email);
        setCode("");
        setInfo("verify.sent");
      } else {
        setError(authErrorKey(err));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pendingEmail) return;
    setError(null);
    setInfo(null);
    setLoading(true);
    try {
      const response = await api.verifyEmail(pendingEmail, code);
      setSession(response.role, response.username);
      navigate("/annonces");
    } catch (err) {
      setError(authErrorKey(err));
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (!pendingEmail) return;
    setError(null);
    try {
      await api.resendCode(pendingEmail);
      setInfo("verify.resent");
    } catch (err) {
      setError(authErrorKey(err));
    }
  };

  return (
    <div className="flex h-full w-full items-center justify-center overflow-y-auto px-4 py-6">
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
              <p className="text-sm text-slate-500">Real Estate Web Scraper</p>
            </div>
          </Link>
        </div>

        <div className="glass rounded-2xl p-8">
          {pendingEmail ? (
            <>
              <div className="mb-6">
                <h1 className="font-display text-2xl font-semibold tracking-tight text-slate-900">
                  {t("verify.title")}
                </h1>
                <p className="mt-2 text-sm text-slate-500">
                  {t("verify.subtitle")}{" "}
                  <span className="font-medium text-slate-700">{pendingEmail}</span>
                </p>
              </div>

              {error && (
                <div className="mb-4 flex items-start gap-2.5 rounded-lg bg-red-500/10 border border-red-500/20 p-3">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
                  <p className="text-sm text-red-600">{t(error)}</p>
                </div>
              )}
              {info && (
                <div className="mb-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3">
                  <p className="text-sm text-emerald-700">{t(info)}</p>
                </div>
              )}

              <form onSubmit={handleVerify} className="space-y-4">
                <div>
                  <label
                    htmlFor="code"
                    className="mb-2 block text-sm font-medium text-slate-700"
                  >
                    {t("verify.codeLabel")}
                  </label>
                  <input
                    id="code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    value={code}
                    onChange={(e) =>
                      setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                    }
                    className="w-full rounded-lg border border-brand-200 bg-white px-4 py-3 text-center text-lg tracking-[0.5em] text-slate-900 placeholder-slate-400 transition focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                    placeholder="______"
                    required
                    minLength={6}
                    maxLength={6}
                  />
                </div>

                <button
                  type="submit"
                  disabled={loading || code.length < 6}
                  className="btn-primary w-full flex items-center justify-center gap-2"
                >
                  {loading ? t("login.loading") : t("verify.submit")}
                </button>
              </form>

              <div className="mt-6 flex items-center justify-between text-sm">
                <button
                  type="button"
                  onClick={handleResend}
                  className="text-slate-500 transition hover:text-slate-900"
                >
                  {t("verify.resend")}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPendingEmail(null);
                    setCode("");
                    setError(null);
                    setInfo(null);
                  }}
                  className="text-slate-500 transition hover:text-slate-900"
                >
                  {t("verify.back")}
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="mb-6">
                <h1 className="font-display text-2xl font-semibold tracking-tight text-slate-900">
                  {isLogin ? t("login.title") : t("login.titleRegister")}
                </h1>
                <p className="mt-2 text-sm text-slate-500">
                  {isLogin ? t("login.subtitle") : t("login.subtitleRegister")}
                </p>
              </div>

              {error && (
                <div className="mb-4 flex items-start gap-2.5 rounded-lg bg-red-500/10 border border-red-500/20 p-3">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
                  <p className="text-sm text-red-600">{t(error)}</p>
                </div>
              )}
              {info && (
                <div className="mb-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3">
                  <p className="text-sm text-emerald-700">{t(info)}</p>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label
                    htmlFor="email"
                    className="mb-2 block text-sm font-medium text-slate-700"
                  >
                    {t("login.email")}
                  </label>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full rounded-lg border border-brand-200 bg-white px-4 py-3 text-slate-900 placeholder-slate-400 transition focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                    placeholder={t("login.emailPlaceholder")}
                    required
                  />
                </div>

                <div>
                  <label
                    htmlFor="password"
                    className="mb-2 block text-sm font-medium text-slate-700"
                  >
                    {t("login.password")}
                  </label>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full rounded-lg border border-brand-200 bg-white px-4 py-3 text-slate-900 placeholder-slate-400 transition focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
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
                    t("login.loading")
                  ) : isLogin ? (
                    <>
                      <LogIn className="h-4 w-4" />
                      {t("login.submit")}
                    </>
                  ) : (
                    <>
                      <UserPlus className="h-4 w-4" />
                      {t("login.submitRegister")}
                    </>
                  )}
                </button>
              </form>

              {googleClientId && (
                <div className="mt-6">
                  <div className="mb-4 flex items-center gap-3">
                    <div className="h-px flex-1 bg-brand-100" />
                    <span className="text-xs text-slate-400">{t("login.or")}</span>
                    <div className="h-px flex-1 bg-brand-100" />
                  </div>
                  <div ref={googleBtnRef} className="flex justify-center" />
                </div>
              )}

              <div className="mt-6 text-center">
                <button
                  type="button"
                  onClick={() => {
                    setIsLogin(!isLogin);
                    setError(null);
                    setInfo(null);
                  }}
                  className="text-sm text-slate-500 transition hover:text-slate-900"
                >
                  {isLogin ? t("login.toggleToRegister") : t("login.toggleToLogin")}
                </button>
              </div>
            </>
          )}
        </div>

        <div className="mt-6 text-center">
          <Link
            to="/"
            className="text-sm text-slate-500 transition hover:text-slate-900"
          >
            {t("login.backHome")}
          </Link>
        </div>
      </div>
    </div>
  );
}
