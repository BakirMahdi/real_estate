import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  Ban,
  CheckCircle2,
  Clock,
  Database,
  Download,
  Loader2,
  Search,
  Server,
  XCircle,
  Lock,
  Users,
  Archive,
  Globe,
} from "lucide-react";
import { API_BASE, api, getAuthToken, isAuthenticated, logout } from "../api/client";
import { formatPrice, governorateOf, sourceLabel, truncate } from "../lib/format";
import type {
  ArchiveSearchFilters,
  HealthStatus,
  Property,
  ScrapeProgress,
  ScrapeResult,
} from "../types/property";

const ARCHIVE_SOURCES = ["tayara", "mubawab", "expat"];

function ArchiveToggle({
  archived,
  onToggle,
}: {
  archived: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={archived}
      aria-label={archived ? "Restaurer l'annonce" : "Archiver l'annonce"}
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-violet-500/40 ${
        archived ? "bg-violet-500" : "bg-slate-600"
      }`}
    >
      <span
        className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
          archived ? "translate-x-[22px]" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

const PHASE_ORDER = ["rent", "sale", "land"] as const;

const PHASE_LABELS: Record<string, string> = {
  rent: "Location",
  sale: "Vente",
  land: "Terrains",
};

const STEP_LABELS: Record<string, string> = {
  listing: "Collecte des pages",
  enriching: "Détails des annonces",
  inserting: "Insertion en base",
};

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
  const [scrapeProgress, setScrapeProgress] = useState<ScrapeProgress | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [scrapeCancelled, setScrapeCancelled] = useState(false);
  const [archiveFilters, setArchiveFilters] = useState({
    ad_id: "",
    name: "",
    location: "",
    min_price: "",
    max_price: "",
    source: "",
  });
  const [archiveResults, setArchiveResults] = useState<Property[] | null>(null);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const scrapingRef = useRef(false);
  const navigate = useNavigate();

  useEffect(() => {
    scrapingRef.current = scraping;
  }, [scraping]);

  // Auto-cancel the scrape if the page is refreshed or closed while it runs.
  // sendBeacon can't set headers, so the JWT goes in the query string; the
  // backend only cancels manually started scrapes through this endpoint.
  useEffect(() => {
    const handlePageHide = () => {
      if (scrapingRef.current) {
        const token = getAuthToken() ?? "";
        navigator.sendBeacon(
          `${API_BASE}/scrape/cancel-beacon?token=${encodeURIComponent(token)}`
        );
      }
    };
    window.addEventListener("pagehide", handlePageHide);
    return () => window.removeEventListener("pagehide", handlePageHide);
  }, []);

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
      if (scrapeStatus.progress) {
        setScrapeProgress(scrapeStatus.progress);
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
            setCancelling(false);
            setScrapeCancelled(Boolean(status.cancelled));
            if (status.results) {
              setScrapeResults(status.results);
            }
            if (status.error) {
              setScrapeError(status.error);
            }
            if (status.progress) {
              setScrapeProgress(status.progress);
            }
            refresh();
          } else {
            if (status.cancel_requested) {
              setCancelling(true);
            }
            if (status.progress) {
              setScrapeProgress(status.progress);
            }
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
    setScrapeCancelled(false);
    setCancelling(false);

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

  const cancelScrape = async () => {
    setCancelling(true);
    try {
      await api.cancelScrape();
    } catch (err) {
      setCancelling(false);
      if (err instanceof Error && err.message === "UNAUTHORIZED") {
        setNeedsAuth(true);
        logout();
      } else {
        setScrapeError(err instanceof Error ? err.message : "Échec de l'annulation du scrape");
      }
    }
  };

  const setArchiveFilter = (key: keyof typeof archiveFilters, value: string) => {
    setArchiveFilters((prev) => ({ ...prev, [key]: value }));
  };

  const resetArchiveFilters = () => {
    setArchiveFilters({
      ad_id: "",
      name: "",
      location: "",
      min_price: "",
      max_price: "",
      source: "",
    });
    setArchiveResults(null);
  };

  const handleArchiveSearch = async () => {
    setArchiveLoading(true);
    try {
      const payload: ArchiveSearchFilters = {
        ad_id: archiveFilters.ad_id.trim() || undefined,
        name: archiveFilters.name.trim() || undefined,
        location: archiveFilters.location.trim() || undefined,
        min_price: archiveFilters.min_price ? Number(archiveFilters.min_price) : undefined,
        max_price: archiveFilters.max_price ? Number(archiveFilters.max_price) : undefined,
        source: archiveFilters.source || undefined,
      };
      const res = await api.adminArchiveSearch(payload);
      setArchiveResults(res.items);
    } catch (err) {
      if (err instanceof Error && err.message === "UNAUTHORIZED") {
        setNeedsAuth(true);
        logout();
      }
      setArchiveResults([]);
    } finally {
      setArchiveLoading(false);
    }
  };

  const toggleArchive = async (property: Property) => {
    const next = !property.archived;
    // Optimistic update so the switch responds instantly.
    setArchiveResults((prev) =>
      prev
        ? prev.map((p) => (p.id === property.id ? { ...p, archived: next } : p))
        : prev,
    );
    try {
      if (next) {
        await api.adminArchive(property.id);
      } else {
        await api.adminUnarchive(property.id);
      }
      // Keep the archived KPI in sync.
      api.getKpis().then(setKpis).catch(() => {});
    } catch (err) {
      // Revert on failure.
      setArchiveResults((prev) =>
        prev
          ? prev.map((p) =>
              p.id === property.id ? { ...p, archived: property.archived } : p,
            )
          : prev,
      );
      if (err instanceof Error && err.message === "UNAUTHORIZED") {
        setNeedsAuth(true);
        logout();
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

      <div className="glass animate-slide-up mb-8 rounded-2xl p-6 shadow-card" style={{ animationDelay: "425ms" }}>
        <div className="mb-2 flex items-center gap-2">
          <Archive className="h-5 w-5 text-violet-400" />
          <h2 className="font-display text-xl font-semibold text-white">Archivage manuel</h2>
        </div>
        <p className="mb-6 text-sm text-slate-400">
          Filtrez les annonces par ID, nom, localisation, prix ou source, puis
          activez l&apos;interrupteur à droite de chaque ligne pour l&apos;archiver
          ou la restaurer. Cliquez sur une ligne pour ouvrir l&apos;annonce.
        </p>

        <div className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">ID</label>
            <input
              type="text"
              placeholder="ID ou ad_id"
              value={archiveFilters.ad_id}
              onChange={(e) => setArchiveFilter("ad_id", e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleArchiveSearch()}
              className="input-field w-full"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Nom</label>
            <input
              type="text"
              placeholder="Titre de l'annonce"
              value={archiveFilters.name}
              onChange={(e) => setArchiveFilter("name", e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleArchiveSearch()}
              className="input-field w-full"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Localisation</label>
            <input
              type="text"
              placeholder="Ville ou adresse"
              value={archiveFilters.location}
              onChange={(e) => setArchiveFilter("location", e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleArchiveSearch()}
              className="input-field w-full"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Prix min (DT)</label>
            <input
              type="number"
              min={0}
              placeholder="0"
              value={archiveFilters.min_price}
              onChange={(e) => setArchiveFilter("min_price", e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleArchiveSearch()}
              className="input-field w-full"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Prix max (DT)</label>
            <input
              type="number"
              min={0}
              placeholder="∞"
              value={archiveFilters.max_price}
              onChange={(e) => setArchiveFilter("max_price", e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleArchiveSearch()}
              className="input-field w-full"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Source</label>
            <select
              value={archiveFilters.source}
              onChange={(e) => setArchiveFilter("source", e.target.value)}
              className="input-field w-full"
            >
              <option value="">Toutes</option>
              {ARCHIVE_SOURCES.map((src) => (
                <option key={src} value={src}>
                  {sourceLabel(src)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mb-6 flex items-center gap-2">
          <button
            type="button"
            onClick={handleArchiveSearch}
            disabled={archiveLoading}
            className="btn-primary disabled:opacity-50"
          >
            {archiveLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            Rechercher
          </button>
          {archiveResults !== null && (
            <button
              type="button"
              onClick={resetArchiveFilters}
              className="rounded-xl px-4 py-2 text-sm text-slate-400 transition hover:text-white"
            >
              Effacer
            </button>
          )}
        </div>

        {archiveLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
          </div>
        ) : archiveResults === null ? null : archiveResults.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500">
            Aucune annonce trouvée pour cette recherche.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-white/5">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/5 bg-slate-900/60 text-xs text-slate-500">
                  <th className="px-4 py-3 font-medium">ID</th>
                  <th className="px-4 py-3 font-medium">Nom</th>
                  <th className="px-4 py-3 font-medium">Localisation</th>
                  <th className="px-4 py-3 font-medium">Prix</th>
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 text-right font-medium">Archivé</th>
                </tr>
              </thead>
              <tbody>
                {archiveResults.map((property) => (
                  <tr
                    key={property.id}
                    onClick={() => navigate(`/property/${property.id}`)}
                    className="cursor-pointer border-b border-white/5 transition last:border-0 hover:bg-slate-800/40"
                  >
                    <td className="px-4 py-3 font-mono text-slate-400">{property.id}</td>
                    <td className="px-4 py-3 font-medium text-white">
                      {truncate(property.title, 45)}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {governorateOf(property)}
                    </td>
                    <td className="px-4 py-3 text-slate-300">{formatPrice(property.price)}</td>
                    <td className="px-4 py-3 text-slate-400">{sourceLabel(property.source)}</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end">
                        <ArchiveToggle
                          archived={Boolean(property.archived)}
                          onToggle={() => toggleArchive(property)}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="glass animate-slide-up rounded-2xl p-6 shadow-card" style={{ animationDelay: "450ms" }}>
        <h2 className="mb-2 font-display text-xl font-semibold text-white">
          Lancer un scrape
        </h2>
        <p className="mb-6 text-sm text-slate-400">
          Chaque site est scrapé en 3 phases : Location, Vente, puis Terrains.
          La base est mise à jour à la fin de chaque phase et la mémoire est
          libérée. Les doublons sont ignorés automatiquement via l&apos;ID source.
          Le détail complet est écrit dans <span className="font-mono text-slate-300">logs/scrape_log.json</span>.
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

        <div className="flex flex-wrap items-center gap-3">
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

          {scraping && (
            <button
              type="button"
              onClick={cancelScrape}
              disabled={cancelling}
              className="inline-flex items-center gap-2 rounded-xl bg-red-500/10 px-4 py-2.5 text-sm font-medium text-red-400 transition hover:bg-red-500/20 disabled:opacity-50"
            >
              {cancelling ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Annulation en cours…
                </>
              ) : (
                <>
                  <Ban className="h-4 w-4" />
                  Annuler le scrape
                </>
              )}
            </button>
          )}
        </div>

        <p className="mt-3 text-xs text-slate-500">
          En cas d&apos;annulation (bouton, actualisation ou fermeture de la page),
          toutes les modifications de ce scrape sont annulées en base.
        </p>

        {scrapeError && (
          <p className="mt-4 text-sm text-red-400">{scrapeError}</p>
        )}

        {scrapeCancelled && !scraping && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-amber-500/10 px-4 py-3 text-sm text-amber-400">
            <Ban className="h-4 w-4 shrink-0" />
            Scrape annulé — toutes les modifications apportées à la base pendant ce scrape ont été annulées.
          </div>
        )}

        {scraping && scrapeProgress && (
          <div className="mt-6 rounded-xl border border-white/5 bg-slate-900/60 p-4">
            <h4 className="mb-3 text-sm font-semibold text-white">Progression du scrape</h4>
            <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
              <span>Sources complétées</span>
              <span>{scrapeProgress.completed_sources}/{scrapeProgress.total_sources}</span>
            </div>
            <div className="space-y-2">
              {Object.entries(scrapeProgress.sources).map(([source, progress]) => (
                <div key={source} className="rounded-lg bg-slate-800/50 px-3 py-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className={`h-2 w-2 rounded-full ${
                        progress.status === 'completed' ? 'bg-emerald-400' :
                        progress.status === 'running' ? 'bg-brand-400 animate-pulse' :
                        progress.status === 'error' ? 'bg-red-400' :
                        progress.status === 'cancelled' ? 'bg-amber-400' :
                        'bg-slate-500'
                      }`} />
                      <span className="text-xs font-medium text-slate-300">{sourceLabel(source)}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-400">
                      {progress.status === 'running' && progress.phase && (
                        <span className="text-brand-400">
                          Phase {PHASE_LABELS[progress.phase] ?? progress.phase}
                          {progress.step ? ` — ${STEP_LABELS[progress.step] ?? progress.step}` : ""}
                          {progress.step === 'enriching' && progress.total_pages > 0
                            ? ` ${progress.pages_processed}/${progress.total_pages}`
                            : progress.step === 'listing'
                              ? ` (${progress.pages_processed} pages)`
                              : ""}
                        </span>
                      )}
                      {progress.status === 'completed' && (
                        <span className="text-emerald-400">Terminé</span>
                      )}
                      {progress.status === 'error' && (
                        <span className="text-red-400">Erreur</span>
                      )}
                      {progress.status === 'cancelled' && (
                        <span className="text-amber-400">Annulé</span>
                      )}
                      {progress.status === 'pending' && (
                        <span className="text-slate-500">En attente</span>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 grid grid-cols-3 gap-2">
                    {PHASE_ORDER.map((phase) => {
                      const stats = progress.phases?.[phase];
                      const phaseStatus = stats?.status ?? 'pending';
                      return (
                        <div
                          key={phase}
                          className={`rounded-md px-2 py-1 text-[11px] ${
                            phaseStatus === 'completed' ? 'bg-emerald-500/10 text-emerald-400' :
                            phaseStatus === 'running' ? 'bg-brand-500/10 text-brand-400' :
                            'bg-slate-900/60 text-slate-500'
                          }`}
                        >
                          <span className="font-medium">{PHASE_LABELS[phase]}</span>
                          {phaseStatus === 'completed' && stats && (
                            <span className="ml-1">
                              {stats.count} · +{stats.inserted}
                            </span>
                          )}
                          {phaseStatus === 'running' && <span className="ml-1">en cours…</span>}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
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
                  <th className="px-4 py-3 font-medium">Phase</th>
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
                  if (result.error) {
                    return (
                      <tr key={result.source} className="border-b border-white/5 last:border-0">
                        <td className="px-4 py-3 font-medium text-white">{sourceLabel(sourceKey)}</td>
                        <td colSpan={6} className="px-4 py-3 text-red-400">{result.error}</td>
                      </tr>
                    );
                  }
                  // Grand-total summary row across every source.
                  if (result.source === "total") {
                    return (
                      <tr key={result.source} className="border-t-2 border-white/10 bg-slate-900/60 font-semibold last:border-b-0">
                        <td className="px-4 py-3 text-white">Total</td>
                        <td className="px-4 py-3" />
                        <td className="px-4 py-3 text-slate-200">{result.count ?? 0}</td>
                        <td className="px-4 py-3 text-emerald-400">{result.inserted ?? 0}</td>
                        <td className="px-4 py-3 text-slate-300">{result.skipped ?? 0}</td>
                        <td className="px-4 py-3 text-amber-400">{result.errors ?? 0}</td>
                        <td className="px-4 py-3 text-violet-400">{result.archived ?? 0}</td>
                      </tr>
                    );
                  }
                  const phaseRows = result.phases
                    ? PHASE_ORDER.filter((phase) => result.phases?.[phase]).map((phase) => {
                        const stats = result.phases![phase];
                        return (
                          <tr key={`${result.source}-${phase}`} className="border-b border-white/5 bg-slate-900/30 text-xs">
                            <td className="px-4 py-2" />
                            <td className="px-4 py-2 text-slate-400">{PHASE_LABELS[phase] ?? phase}</td>
                            <td className="px-4 py-2 text-slate-400">{stats.count}</td>
                            <td className="px-4 py-2 text-emerald-400/80">{stats.inserted}</td>
                            <td className="px-4 py-2 text-slate-500">{stats.skipped}</td>
                            <td className="px-4 py-2 text-amber-400/80">{stats.errors}</td>
                            <td className="px-4 py-2" />
                          </tr>
                        );
                      })
                    : [];
                  return (
                    <Fragment key={result.source}>
                      <tr className="border-b border-white/5">
                        <td className="px-4 py-3 font-medium text-white">
                          {sourceLabel(sourceKey)}
                        </td>
                        <td className="px-4 py-3 text-slate-500">Total</td>
                        <td className="px-4 py-3 text-slate-300">{result.count}</td>
                        <td className="px-4 py-3 text-emerald-400">{result.inserted}</td>
                        <td className="px-4 py-3 text-slate-400">{result.skipped}</td>
                        <td className="px-4 py-3 text-amber-400">{result.errors}</td>
                        <td className="px-4 py-3 text-violet-400">{result.archived || 0}</td>
                      </tr>
                      {phaseRows}
                    </Fragment>
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
