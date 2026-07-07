import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  CheckCircle2,
  Clock,
  Database,
  Download,
  Loader2,
  Server,
  XCircle,
  Lock,
  Users,
  Archive,
  Globe,
} from "lucide-react";
import { api, isAuthenticated, logout } from "../api/client";
import { sourceLabel } from "../lib/format";
import type { HealthStatus, ScrapeResult } from "../types/property";

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div
      className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium ${
        ok
          ? "bg-emerald-500/10 text-emerald-400"
          : "bg-red-500/10 text-red-400"
      }`}
    >
      {ok ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
      {label}
    </div>
  );
}

export function DashboardPage() {
  const [apiHealth, setApiHealth] = useState<HealthStatus | null>(null);
  const [dbHealth, setDbHealth] = useState<HealthStatus | null>(null);
  const [totalProperties, setTotalProperties] = useState(0);
  const [scrapeResults, setScrapeResults] = useState<ScrapeResult[] | null>(null);
  const [scraping, setScraping] = useState(false);
  const [scrapeDuration, setScrapeDuration] = useState(0);
  const [scrapeError, setScrapeError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nextScrapeTime, setNextScrapeTime] = useState<number | null>(null);
  const [timeLeft, setTimeLeft] = useState<number>(0);
  const [needsAuth, setNeedsAuth] = useState(!isAuthenticated());
  const [passwordInput, setPasswordInput] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [kpis, setKpis] = useState<{
    properties_by_type: Record<string, number>;
    archived_count: number;
    user_count: number;
    ads_by_source: Record<string, number>;
  } | null>(null);

  const refresh = useCallback(async () => {
    if (!isAuthenticated()) {
      setNeedsAuth(true);
      return;
    }
    setLoading(true);
    try {
      const [health, dbStatus, props, scrapeStatus, kpisData] = await Promise.all([
        api.health(),
        api.healthDb(),
        api.getAllProperties(),
        api.getScrapeStatus(),
        api.getKpis(),
      ]);
      setApiHealth(health);
      setDbHealth(dbStatus);
      setTotalProperties(props.count);
      setKpis(kpisData);
      if (scrapeStatus.next_scrape_time !== undefined) {
        setNextScrapeTime(scrapeStatus.next_scrape_time);
      }

      if (scrapeStatus.is_scraping) {
        setScraping(true);
      } else if (scrapeStatus.results && !scrapeResults) {
        setScrapeResults(scrapeStatus.results);
      }
    } catch (err) {
      if (err instanceof Error && err.message === "UNAUTHORIZED") {
        setNeedsAuth(true);
        logout();
      } else {
        setApiHealth(null);
        setDbHealth(null);
      }
    } finally {
      setLoading(false);
    }
  }, [scrapeResults]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    let timerInterval: ReturnType<typeof setInterval>;
    if (scraping) {
      timerInterval = setInterval(() => {
        setScrapeDuration((prev) => prev + 1);
      }, 1000);
    }
    return () => clearInterval(timerInterval);
  }, [scraping]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;

    if (scraping) {
      interval = setInterval(async () => {
        try {
          const status = await api.getScrapeStatus();
          if (status.next_scrape_time !== undefined) {
            setNextScrapeTime(status.next_scrape_time);
          }
          if (!status.is_scraping) {
            setScraping(false);
            if (status.results) {
              setScrapeResults(status.results);
            }
            if (status.error) {
              setScrapeError(status.error);
            }
            refresh();
          }
        } catch (err) {
          if (err instanceof Error && err.message === "UNAUTHORIZED") {
            setNeedsAuth(true);
            logout();
          }
          console.error("Error polling scrape status:", err);
        }
      }, 2000);
    }

    return () => clearInterval(interval);
  }, [scraping, refresh]);

  useEffect(() => {
    if (!nextScrapeTime) return;

    const updateCountdown = () => {
      const diff = Math.max(0, Math.floor(nextScrapeTime - Date.now() / 1000));
      setTimeLeft(diff);

      if (diff === 0) {
        const timeout = setTimeout(() => {
          refresh();
        }, 2000);
        return () => clearTimeout(timeout);
      }
    };

    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, [nextScrapeTime, refresh]);

  const formatCountdown = (seconds: number) => {
    if (seconds <= 0) return "Démarrage…";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    
    const pad = (num: number) => String(num).padStart(2, "0");
    if (h > 0) {
      return `${pad(h)}:${pad(m)}:${pad(s)}`;
    }
    return `${pad(m)}:${pad(s)}`;
  };

  const runScrape = async () => {
    setScrapeError(null);
    setScrapeResults(null);
    setScrapeDuration(0);

    try {
      await api.scrape();
      setScraping(true);
    } catch (err) {
      if (err instanceof Error && err.message === "UNAUTHORIZED") {
        setNeedsAuth(true);
        logout();
      } else {
        setScrapeError(err instanceof Error ? err.message : "Échec du démarrage du scrape");
      }
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!passwordInput) return;
    
    setAuthError(null);
    setIsAuthenticating(true);
    
    try {
      const response = await api.login("admin", passwordInput);
      // Store the token
      const token = response.access_token;
      localStorage.setItem("auth_token", token);
      localStorage.setItem("user_role", response.role);
      setNeedsAuth(false);
      refresh();
    } catch (err) {
      setAuthError("Mot de passe incorrect. Veuillez réessayer.");
    } finally {
      setIsAuthenticating(false);
    }
  };

  const apiOk = apiHealth?.status === "ok";
  const dbOk = dbHealth?.status === "ok";

  if (needsAuth) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 sm:px-6">
        <div className="glass rounded-2xl p-8 shadow-card text-center animate-fade-in">
          <div className="mb-4 mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-brand-500/20">
            <Lock className="h-6 w-6 text-brand-400" />
          </div>
          <h2 className="mb-2 font-display text-2xl font-semibold text-white">Authentification requise</h2>
          <p className="mb-6 text-sm text-slate-400">
            Veuillez vous connecter pour accéder au dashboard.
          </p>
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <input
              type="password"
              placeholder="Mot de passe"
              value={passwordInput}
              onChange={(e) => setPasswordInput(e.target.value)}
              className={`w-full rounded-xl border bg-slate-900/50 px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:ring-1 ${authError ? "border-red-500/50 focus:border-red-500 focus:ring-red-500" : "border-white/10 focus:border-brand-500 focus:ring-brand-500"}`}
              autoFocus
              disabled={isAuthenticating}
            />
            {authError && (
              <p className="text-left text-sm text-red-400">{authError}</p>
            )}
            <button type="submit" disabled={isAuthenticating || !passwordInput} className="btn-primary w-full justify-center disabled:opacity-50">
              {isAuthenticating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Vérification…
                </>
              ) : (
                "Se connecter"
              )}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <section className="mb-10 animate-fade-in">
        <div className="mb-2 flex items-center gap-2 text-sm text-brand-400">
          <Activity className="h-4 w-4" />
          Administration
        </div>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-white">
          Dashboard
        </h1>
        <p className="mt-3 text-slate-400">
          Surveillez l&apos;état du système et lancez la collecte d&apos;annonces.
        </p>
      </section>

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <div className="stat-card animate-slide-up">
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600/20">
            <Server className="h-5 w-5 text-brand-400" />
          </div>
          <p className="text-xs text-slate-500">API</p>
          {loading ? (
            <Loader2 className="mt-2 h-5 w-5 animate-spin text-slate-500" />
          ) : (
            <StatusBadge ok={apiOk} label={apiOk ? "En ligne" : "Hors ligne"} />
          )}
        </div>

        <div
          className="stat-card animate-slide-up"
          style={{ animationDelay: "50ms" }}
        >
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600/20">
            <Database className="h-5 w-5 text-violet-400" />
          </div>
          <p className="text-xs text-slate-500">Base de données</p>
          {loading ? (
            <Loader2 className="mt-2 h-5 w-5 animate-spin text-slate-500" />
          ) : (
            <StatusBadge ok={dbOk} label={dbOk ? "Connectée" : "Indisponible"} />
          )}
        </div>

        <div
          className="stat-card animate-slide-up"
          style={{ animationDelay: "100ms" }}
        >
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-amber-600/20">
            <Download className="h-5 w-5 text-amber-400" />
          </div>
          <p className="text-xs text-slate-500">Annonces en base</p>
          <p className="mt-2 font-display text-3xl font-semibold text-white">
            {loading ? "—" : totalProperties}
          </p>
        </div>
      </div>

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <div className="stat-card animate-slide-up" style={{ animationDelay: "150ms" }}>
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600/20">
            <Archive className="h-5 w-5 text-emerald-400" />
          </div>
          <p className="text-xs text-slate-500">Annonces archivées</p>
          <p className="mt-2 font-display text-3xl font-semibold text-white">
            {loading ? "—" : kpis?.archived_count ?? 0}
          </p>
        </div>

        <div className="stat-card animate-slide-up" style={{ animationDelay: "200ms" }}>
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600/20">
            <Users className="h-5 w-5 text-blue-400" />
          </div>
          <p className="text-xs text-slate-500">Utilisateurs inscrits</p>
          <p className="mt-2 font-display text-3xl font-semibold text-white">
            {loading ? "—" : kpis?.user_count ?? 0}
          </p>
        </div>

        <div className="stat-card animate-slide-up" style={{ animationDelay: "250ms" }}>
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-600/20">
            <Globe className="h-5 w-5 text-cyan-400" />
          </div>
          <p className="text-xs text-slate-500">Sources actives</p>
          <p className="mt-2 font-display text-3xl font-semibold text-white">
            {loading ? "—" : Object.keys(kpis?.ads_by_source ?? {}).length}
          </p>
        </div>
      </div>

      {kpis && !loading && (
        <div className="mb-8 grid gap-4 sm:grid-cols-2">
          <div className="glass animate-slide-up rounded-2xl p-6 shadow-card" style={{ animationDelay: "350ms" }}>
            <h3 className="mb-4 font-display text-lg font-semibold text-white">Propriétés par type</h3>
            <div className="space-y-3">
              {Object.entries(kpis.properties_by_type).map(([type, count]) => (
                <div key={type} className="flex items-center justify-between">
                  <span className="text-sm text-slate-300">{type}</span>
                  <span className="font-display text-lg font-semibold text-white">{count}</span>
                </div>
              ))}
              {Object.keys(kpis.properties_by_type).length === 0 && (
                <p className="text-sm text-slate-500">Aucune donnée disponible</p>
              )}
            </div>
          </div>

          <div className="glass animate-slide-up rounded-2xl p-6 shadow-card" style={{ animationDelay: "400ms" }}>
            <h3 className="mb-4 font-display text-lg font-semibold text-white">Annonces par source</h3>
            <div className="space-y-3">
              {Object.entries(kpis.ads_by_source).map(([source, count]) => (
                <div key={source} className="flex items-center justify-between">
                  <span className="text-sm text-slate-300">{sourceLabel(source)}</span>
                  <span className="font-display text-lg font-semibold text-white">{count}</span>
                </div>
              ))}
              {Object.keys(kpis.ads_by_source).length === 0 && (
                <p className="text-sm text-slate-500">Aucune donnée disponible</p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="glass animate-slide-up rounded-2xl p-6 shadow-card" style={{ animationDelay: "450ms" }}>
        <h2 className="mb-2 font-display text-xl font-semibold text-white">
          Lancer un scrape
        </h2>
        <p className="mb-6 text-sm text-slate-400">
          Collecte les nouvelles annonces depuis Tayara et Mubawab. Les doublons
          sont ignorés automatiquement via l&apos;ID source.
        </p>

        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-t border-b border-white/5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600/10">
              <Clock className="h-4 w-4 text-brand-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-300">Scrape automatique</p>
              <p className="text-xs text-slate-500">Chaque lundi à 00h00</p>
            </div>
          </div>
          <div className="flex flex-col sm:items-end">
            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Prochain scrape automatique dans</span>
            <p className="font-mono text-xl font-bold text-brand-400">
              {nextScrapeTime ? formatCountdown(timeLeft) : "Calcul en cours…"}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={runScrape}
          disabled={scraping}
          className="btn-primary"
        >
          {scraping ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Scrape en cours… ({scrapeDuration}s)
            </>
          ) : (
            <>
              <Download className="h-4 w-4" />
              Démarrer le scrape
            </>
          )}
        </button>

        {scrapeError && (
          <p className="mt-4 text-sm text-red-400">{scrapeError}</p>
        )}

        {scrapeResults && (
          <div className="mt-6 overflow-hidden rounded-xl border border-white/5">
            {scrapeDuration > 0 && (
              <div className="bg-slate-900/60 px-4 py-3 text-sm text-slate-300 font-medium border-b border-white/5">
                Terminé en {scrapeDuration} secondes.
              </div>
            )}
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/5 bg-slate-900/60 text-xs text-slate-500">
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 font-medium">Trouvées</th>
                  <th className="px-4 py-3 font-medium">Insérées</th>
                  <th className="px-4 py-3 font-medium">Déjà en base</th>
                  <th className="px-4 py-3 font-medium">Erreurs</th>
                  <th className="px-4 py-3 font-medium">Archivées</th>
                </tr>
              </thead>
              <tbody>
                {scrapeResults.map((result) => {
                  const sourceKey = result.source.replace("scrape_", "");
                  return (
                    <tr key={result.source} className="border-b border-white/5 last:border-0">
                      <td className="px-4 py-3 font-medium text-white">
                        {sourceLabel(sourceKey)}
                      </td>
                      {result.error ? (
                        <td colSpan={5} className="px-4 py-3 text-red-400">
                          {result.error}
                        </td>
                      ) : (
                        <>
                          <td className="px-4 py-3 text-slate-300">{result.count}</td>
                          <td className="px-4 py-3 text-emerald-400">{result.inserted}</td>
                          <td className="px-4 py-3 text-slate-400">{result.skipped}</td>
                          <td className="px-4 py-3 text-amber-400">{result.errors}</td>
                          <td className="px-4 py-3 text-violet-400">{result.archived || 0}</td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="border-t border-white/5 px-4 py-3 text-xs text-slate-500">
              « Déjà en base » = annonce déjà enregistrée (même source + id). Les doublons entre
              vente et location sont filtrés avant l&apos;insertion.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
