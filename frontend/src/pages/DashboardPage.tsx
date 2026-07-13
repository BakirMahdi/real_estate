import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import DataTable from "datatables.net-react";
import type { DataTableRef } from "datatables.net-react";
import DT from "datatables.net-dt";
import type { AjaxData, AjaxResponse, Config } from "datatables.net-dt";
import "datatables.net-dt/css/dataTables.dataTables.css";
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
  X,
  XCircle,
  Lock,
  Users,
  Archive,
  ArchiveRestore,
  Globe,
} from "lucide-react";
import {
  API_BASE,
  api,
  isAuthenticated,
  logout,
  setSession,
} from "../api/client";
import {
  formatArea,
  formatPrice,
  GOVERNORATE_NAMES,
  governorateOf,
  listingTypeLabel,
  sourceLabel,
  subcategoryLabel,
  truncate,
} from "../lib/format";
import { useLang } from "../lib/i18n";
import type {
  HealthStatus,
  Property,
  ScrapeProgress,
  ScrapeResult,
} from "../types/property";

DataTable.use(DT);

interface ArchiveRow {
  id: number;
  title: string;
  location: string;
  categoryLabel: string;
  transactionLabel: string;
  priceLabel: string;
  areaLabel: string;
  bedroomsLabel: string;
  sourceLabel: string;
  archived: boolean;
  property: Property;
}

function toArchiveRow(property: Property): ArchiveRow {
  return {
    id: property.id,
    title: truncate(property.title, 60),
    location: governorateOf(property),
    categoryLabel: subcategoryLabel(property.subcategory, property.property_type),
    transactionLabel: listingTypeLabel(property.listing_type),
    priceLabel: formatPrice(property.price),
    areaLabel: formatArea(property.area),
    bedroomsLabel: property.bedrooms != null ? String(property.bedrooms) : "—",
    sourceLabel: sourceLabel(property.source),
    archived: Boolean(property.archived),
    property,
  };
}

// Maps archiveColumns[i].data to the backend's sort_by key (the archive
// toggle column is intentionally not orderable and has no entry).
const ARCHIVE_SORT_KEYS: Record<string, string> = {
  id: "id",
  title: "title",
  location: "location",
  categoryLabel: "subcategory",
  transactionLabel: "listing_type",
  priceLabel: "price",
  areaLabel: "area",
  bedroomsLabel: "bedrooms",
  sourceLabel: "source",
};

interface ArchiveFilters {
  city?: string;
  subcategory?: string;
  listingType?: string;
  minPrice?: number;
  maxPrice?: number;
  minArea?: number;
  maxArea?: number;
  bedrooms?: number;
}

interface ArchiveTableState {
  search: string;
  archivedOnly: boolean;
  start: number;
  length: number;
  orderCol: number;
  orderDir: "asc" | "desc";
  filters?: ArchiveFilters;
}

// Persists the archive table's search/filter/paging/sort state across
// navigation (e.g. opening an ad's detail page and coming back) so the admin
// doesn't have to redo their search. sessionStorage rather than the URL to
// keep this self-contained; scoped to the current tab/session.
const ARCHIVE_STATE_KEY = "rews_archive_table_state";

function loadArchiveTableState(): ArchiveTableState | null {
  try {
    const raw = sessionStorage.getItem(ARCHIVE_STATE_KEY);
    return raw ? (JSON.parse(raw) as ArchiveTableState) : null;
  } catch {
    return null;
  }
}

function saveArchiveTableState(state: ArchiveTableState) {
  try {
    sessionStorage.setItem(ARCHIVE_STATE_KEY, JSON.stringify(state));
  } catch {
    // sessionStorage unavailable (e.g. private mode) — not persisting is fine
  }
}

function ArchiveToggle({
  archived,
  onToggle,
}: {
  archived: boolean;
  onToggle: () => void;
}) {
  const { t } = useLang();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={archived}
      aria-label={archived ? t("dashboard.restoreAd") : t("dashboard.archiveAd")}
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-violet-500/40 ${
        archived ? "bg-violet-500" : "bg-slate-300"
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

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div
      className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium ${
        ok ? "bg-emerald-500/10 text-emerald-600" : "bg-red-500/10 text-red-600"
      }`}
    >
      {ok ? (
        <CheckCircle2 className="h-4 w-4" />
      ) : (
        <XCircle className="h-4 w-4" />
      )}
      {label}
    </div>
  );
}

export function DashboardPage() {
  const [apiHealth, setApiHealth] = useState<HealthStatus | null>(null);
  const [dbHealth, setDbHealth] = useState<HealthStatus | null>(null);
  const [totalProperties, setTotalProperties] = useState(0);
  const [scrapeResults, setScrapeResults] = useState<ScrapeResult[] | null>(
    null,
  );
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
  const [scrapeProgress, setScrapeProgress] = useState<ScrapeProgress | null>(
    null,
  );
  const [cancelling, setCancelling] = useState(false);
  const [retraining, setRetraining] = useState(false);
  const [scrapeCancelled, setScrapeCancelled] = useState(false);
  const [restoredArchiveState] = useState(() => loadArchiveTableState());
  const [showArchivedOnly, setShowArchivedOnly] = useState(
    () => restoredArchiveState?.archivedOnly ?? false,
  );
  const [archiveSearchTerm, setArchiveSearchTerm] = useState(
    () => restoredArchiveState?.search ?? "",
  );
  const [archiveFilters, setArchiveFiltersState] = useState<ArchiveFilters>(
    () => restoredArchiveState?.filters ?? {},
  );
  const scrapingRef = useRef(false);
  const showArchivedOnlyRef = useRef(
    restoredArchiveState?.archivedOnly ?? false,
  );
  const archiveFiltersRef = useRef<ArchiveFilters>(archiveFilters);
  const archiveSearchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const archiveTableRef = useRef<DataTableRef>(null);
  const navigate = useNavigate();
  const { t, lang } = useLang();

  const phaseLabel = (phase: string) =>
    ({
      rent: t("dashboard.phaseRent"),
      sale: t("dashboard.phaseSale"),
      land: t("dashboard.phaseLand"),
    })[phase] ?? phase;
  const stepLabel = (step: string) =>
    ({
      listing: t("dashboard.stepListing"),
      enriching: t("dashboard.stepEnriching"),
      inserting: t("dashboard.stepInserting"),
    })[step] ?? step;
  const propertyTypeLabel = (type: string) =>
    ({
      house: t("dashboard.typeHouse"),
      land: t("dashboard.typeLand"),
      apartment: t("dashboard.typeApartment"),
      studio: t("dashboard.typeStudio"),
      office: t("dashboard.typeOffice"),
    })[type] ?? type;

  useEffect(() => {
    scrapingRef.current = scraping;
  }, [scraping]);

  // Auto-cancel the scrape if the page is refreshed or closed while it runs.
  // sendBeacon can't set headers, but a same-origin beacon automatically
  // carries the HttpOnly auth cookie, so the backend still authenticates it;
  // it only cancels manually started scrapes through this endpoint.
  useEffect(() => {
    const handlePageHide = () => {
      if (scrapingRef.current) {
        navigator.sendBeacon(`${API_BASE}/scrape/cancel-beacon`);
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
      // allSettled (not all): one endpoint failing shouldn't wrongly blank
      // out the others' already-healthy state (e.g. a transient KPI query
      // error used to make the API/DB status cards falsely show "Offline").
      const [healthResult, dbResult, propsResult, scrapeResult, kpisResult] =
        await Promise.allSettled([
          api.health(),
          api.healthDb(),
          api.getAllProperties(),
          api.getScrapeStatus(),
          api.getKpis(),
        ]);

      const results = [healthResult, dbResult, propsResult, scrapeResult, kpisResult];
      const unauthorized = results.some(
        (r) => r.status === "rejected" && r.reason instanceof Error && r.reason.message === "UNAUTHORIZED"
      );
      if (unauthorized) {
        setNeedsAuth(true);
        logout();
        return;
      }

      setApiHealth(healthResult.status === "fulfilled" ? healthResult.value : null);
      setDbHealth(dbResult.status === "fulfilled" ? dbResult.value : null);

      if (propsResult.status === "fulfilled") {
        setTotalProperties(propsResult.value.count);
      }
      if (kpisResult.status === "fulfilled") {
        setKpis(kpisResult.value);
      }
      if (scrapeResult.status === "fulfilled") {
        const scrapeStatus = scrapeResult.value;
        if (scrapeStatus.next_scrape_time !== undefined) {
          setNextScrapeTime(scrapeStatus.next_scrape_time);
        }
        if (scrapeStatus.progress) {
          setScrapeProgress(scrapeStatus.progress);
        }

        setRetraining(Boolean(scrapeStatus.training));
        if (scrapeStatus.is_scraping) {
          setScraping(true);
        } else if (scrapeStatus.results && !scrapeResults) {
          setScrapeResults(scrapeStatus.results);
        }
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
          setRetraining(Boolean(status.training));
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

    // Once the countdown hits 0, schedule exactly one refresh 2s later - the
    // `refreshTimeout` guard stops every subsequent 1s tick (diff stays 0
    // until `refresh()` eventually updates nextScrapeTime) from stacking up
    // another uncancelled timeout, which previously turned into an ~1/sec
    // polling loop against 5 endpoints.
    let refreshTimeout: ReturnType<typeof setTimeout> | undefined;

    const updateCountdown = () => {
      const diff = Math.max(0, Math.floor(nextScrapeTime - Date.now() / 1000));
      setTimeLeft(diff);

      if (diff === 0 && refreshTimeout === undefined) {
        refreshTimeout = setTimeout(() => {
          refresh();
        }, 2000);
      }
    };

    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => {
      clearInterval(interval);
      if (refreshTimeout !== undefined) clearTimeout(refreshTimeout);
    };
  }, [nextScrapeTime, refresh]);

  const formatCountdown = (seconds: number) => {
    if (seconds <= 0) return t("dashboard.starting");
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
        setScrapeError(
          err instanceof Error ? err.message : t("dashboard.startFailed"),
        );
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
        setScrapeError(
          err instanceof Error ? err.message : t("dashboard.cancelFailed"),
        );
      }
    }
  };

  const handleArchiveSearchChange = (value: string) => {
    setArchiveSearchTerm(value);
    if (archiveSearchDebounceRef.current) {
      clearTimeout(archiveSearchDebounceRef.current);
    }
    archiveSearchDebounceRef.current = setTimeout(() => {
      archiveTableRef.current?.dt()?.search(value).draw();
    }, 200);
  };

  const setArchivedOnly = (value: boolean) => {
    showArchivedOnlyRef.current = value;
    setShowArchivedOnly(value);
    archiveTableRef.current?.dt()?.ajax.reload();
  };

  const setArchiveFilters = (next: ArchiveFilters) => {
    archiveFiltersRef.current = next;
    setArchiveFiltersState(next);
    archiveTableRef.current?.dt()?.draw();
  };

  const resetArchiveFilters = () => setArchiveFilters({});

  const toggleArchive = async (property: Property) => {
    try {
      if (property.archived) {
        await api.adminUnarchive(property.id);
      } else {
        await api.adminArchive(property.id);
      }
      // Reload the current page in place (keeps search/sort/paging) so the
      // toggled row's state and the archived-only filter stay accurate.
      archiveTableRef.current?.dt()?.ajax.reload(undefined, false);
      api
        .getKpis()
        .then(setKpis)
        .catch(() => {});
    } catch (err) {
      if (err instanceof Error && err.message === "UNAUTHORIZED") {
        setNeedsAuth(true);
        logout();
      }
    }
  };

  const archiveColumns: Config["columns"] = [
    // Kept but hidden (not a visible column) so the default "newest first"
    // sort still works without exposing the raw id to the admin.
    { data: "id", title: "ID", visible: false },
    { data: "title", title: t("dashboard.colName"), className: "font-medium text-slate-900" },
    { data: "location", title: t("dashboard.colLocation") },
    { data: "categoryLabel", title: t("dashboard.colCategory") },
    { data: "transactionLabel", title: t("dashboard.colTransaction") },
    { data: "priceLabel", title: t("dashboard.colPrice") },
    { data: "areaLabel", title: t("dashboard.colArea") },
    { data: "bedroomsLabel", title: t("dashboard.colBedrooms") },
    { data: "sourceLabel", title: t("dashboard.colSource") },
    {
      data: "archived",
      title: t("dashboard.colArchived"),
      orderable: false,
      className: "text-right",
    },
  ];

  const archiveAjax = useCallback(
    (rawData: object, callback: (response: AjaxResponse) => void) => {
      const data = rawData as AjaxData;
      const orderSpec = data.order?.[0];
      const columnKey = orderSpec
        ? (archiveColumns[orderSpec.column]?.data as string | undefined)
        : undefined;
      api
        .adminArchiveSearch({
          search: data.search?.value || undefined,
          archivedOnly: showArchivedOnlyRef.current,
          offset: data.start,
          limit: data.length,
          sortBy: columnKey ? ARCHIVE_SORT_KEYS[columnKey] : undefined,
          sortDir: orderSpec?.dir === "asc" ? "asc" : "desc",
          ...archiveFiltersRef.current,
        })
        .then((res) => {
          callback({
            draw: data.draw,
            recordsTotal: res.total,
            recordsFiltered: res.total_filtered,
            data: res.items.map(toArchiveRow),
          });
        })
        .catch((err) => {
          if (err instanceof Error && err.message === "UNAUTHORIZED") {
            setNeedsAuth(true);
            logout();
          }
          callback({
            draw: data.draw,
            recordsTotal: 0,
            recordsFiltered: 0,
            data: [],
          });
        });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const handleArchiveDraw = useCallback(() => {
    const dt = archiveTableRef.current?.dt();
    if (!dt) return;
    const orderSpec = dt.order()[0];
    const pageInfo = dt.page.info();
    saveArchiveTableState({
      search: String(dt.search() ?? ""),
      archivedOnly: showArchivedOnlyRef.current,
      start: pageInfo.start,
      length: pageInfo.length,
      orderCol: orderSpec ? orderSpec[0] : 0,
      orderDir: orderSpec?.[1] === "asc" ? "asc" : "desc",
      filters: archiveFiltersRef.current,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const archiveTableOptions: Config = {
    serverSide: true,
    processing: true,
    ajax: archiveAjax,
    paging: true,
    pageLength: restoredArchiveState?.length ?? 10,
    lengthMenu: [10, 25, 50, 100],
    order: [
      [
        restoredArchiveState?.orderCol ?? 0,
        restoredArchiveState?.orderDir ?? "desc",
      ],
    ],
    displayStart: restoredArchiveState?.start ?? 0,
    search: { search: restoredArchiveState?.search ?? "" },
    layout: {
      topEnd: null,
    },
    language: {
      processing: t("dashboard.dtProcessing"),
      lengthMenu: t("dashboard.dtLengthMenu"),
      info: t("dashboard.dtInfo"),
      infoEmpty: t("dashboard.dtInfoEmpty"),
      infoFiltered: t("dashboard.dtInfoFiltered"),
      zeroRecords: t("dashboard.dtZeroRecords"),
      paginate: {
        first: t("dashboard.dtFirst"),
        last: t("dashboard.dtLast"),
        next: t("dashboard.dtNext"),
        previous: t("dashboard.dtPrevious"),
      },
    },
    createdRow: (row, data) => {
      const rowData = data as ArchiveRow;
      row.classList.add("cursor-pointer");
      row.addEventListener("click", () => navigate(`/property/${rowData.id}`));
    },
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!passwordInput) return;

    setAuthError(null);
    setIsAuthenticating(true);

    try {
      const response = await api.login("admin", passwordInput);
      // The JWT is set as an HttpOnly cookie by the backend; keep only
      // non-sensitive UI state locally.
      setSession(response.role, response.username);
      setNeedsAuth(false);
      refresh();
    } catch (err) {
      setAuthError(t("dashboard.wrongPassword"));
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
          <h2 className="mb-2 font-display text-2xl font-semibold text-slate-900">
            {t("dashboard.authRequired")}
          </h2>
          <p className="mb-6 text-sm text-slate-500">
            {t("dashboard.authSubtitle")}
          </p>
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <input
              type="password"
              placeholder={t("dashboard.passwordPlaceholder")}
              value={passwordInput}
              onChange={(e) => setPasswordInput(e.target.value)}
              className={`w-full rounded-xl border bg-white px-4 py-3 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 ${authError ? "border-red-500/50 focus:border-red-500 focus:ring-red-500" : "border-slate-200 focus:border-brand-500 focus:ring-brand-500"}`}
              autoFocus
              disabled={isAuthenticating}
            />
            {authError && (
              <p className="text-left text-sm text-red-600">{authError}</p>
            )}
            <button
              type="submit"
              disabled={isAuthenticating || !passwordInput}
              className="btn-primary w-full justify-center disabled:opacity-50"
            >
              {isAuthenticating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t("dashboard.verifying")}
                </>
              ) : (
                t("dashboard.signIn")
              )}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <section className="mb-10 animate-fade-in">
        <div className="mb-2 flex items-center gap-2 text-sm text-brand-400">
          <Activity className="h-4 w-4" />
          {t("dashboard.administration")}
        </div>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-slate-900">
          {t("dashboard.title")}
        </h1>
      </section>

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <div className="stat-card animate-slide-up">
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600/20">
            <Server className="h-5 w-5 text-brand-400" />
          </div>
          <p className="text-xs text-slate-400">API</p>
          {loading ? (
            <Loader2 className="mt-2 h-5 w-5 animate-spin text-slate-400" />
          ) : (
            <StatusBadge
              ok={apiOk}
              label={apiOk ? t("dashboard.online") : t("dashboard.offline")}
            />
          )}
        </div>

        <div
          className="stat-card animate-slide-up"
          style={{ animationDelay: "50ms" }}
        >
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600/20">
            <Database className="h-5 w-5 text-violet-600" />
          </div>
          <p className="text-xs text-slate-400">{t("dashboard.database")}</p>
          {loading ? (
            <Loader2 className="mt-2 h-5 w-5 animate-spin text-slate-400" />
          ) : (
            <StatusBadge
              ok={dbOk}
              label={dbOk ? t("dashboard.connected") : t("dashboard.unavailable")}
            />
          )}
        </div>

        <div
          className="stat-card animate-slide-up"
          style={{ animationDelay: "100ms" }}
        >
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-amber-600/20">
            <Download className="h-5 w-5 text-amber-600" />
          </div>
          <p className="text-xs text-slate-400">{t("dashboard.totalAds")}</p>
          <p className="mt-2 font-display text-3xl font-semibold text-slate-900">
            {loading ? "—" : totalProperties}
          </p>
        </div>
      </div>

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <div
          className="stat-card animate-slide-up"
          style={{ animationDelay: "150ms" }}
        >
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600/20">
            <Archive className="h-5 w-5 text-emerald-600" />
          </div>
          <p className="text-xs text-slate-400">{t("dashboard.archivedAds")}</p>
          <p className="mt-2 font-display text-3xl font-semibold text-slate-900">
            {loading ? "—" : (kpis?.archived_count ?? 0)}
          </p>
        </div>

        <div
          className="stat-card animate-slide-up"
          style={{ animationDelay: "200ms" }}
        >
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600/20">
            <Users className="h-5 w-5 text-blue-600" />
          </div>
          <p className="text-xs text-slate-400">{t("dashboard.users")}</p>
          <p className="mt-2 font-display text-3xl font-semibold text-slate-900">
            {loading ? "—" : (kpis?.user_count ?? 0)}
          </p>
        </div>

        <div
          className="stat-card animate-slide-up"
          style={{ animationDelay: "250ms" }}
        >
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-600/20">
            <Globe className="h-5 w-5 text-cyan-600" />
          </div>
          <p className="text-xs text-slate-400">{t("dashboard.activeSources")}</p>
          <p className="mt-2 font-display text-3xl font-semibold text-slate-900">
            {loading ? "—" : Object.keys(kpis?.ads_by_source ?? {}).length}
          </p>
        </div>
      </div>

      {kpis && !loading && (
        <div className="mb-8 grid gap-4 sm:grid-cols-2">
          <div
            className="glass animate-slide-up rounded-2xl p-6 shadow-card"
            style={{ animationDelay: "350ms" }}
          >
            <h3 className="mb-4 font-display text-lg font-semibold text-slate-900">
              {t("dashboard.propsByType")}
            </h3>
            <div className="space-y-3">
              {Object.entries(kpis.properties_by_type).map(([type, count]) => (
                <div key={type} className="flex items-center justify-between">
                  <span className="text-sm text-slate-700">{propertyTypeLabel(type)}</span>
                  <span className="font-display text-lg font-semibold text-slate-900">
                    {count}
                  </span>
                </div>
              ))}
              {Object.keys(kpis.properties_by_type).length === 0 && (
                <p className="text-sm text-slate-400">
                  {t("dashboard.noData")}
                </p>
              )}
            </div>
          </div>

          <div
            className="glass animate-slide-up rounded-2xl p-6 shadow-card"
            style={{ animationDelay: "400ms" }}
          >
            <h3 className="mb-4 font-display text-lg font-semibold text-slate-900">
              {t("dashboard.adsBySource")}
            </h3>
            <div className="space-y-3">
              {Object.entries(kpis.ads_by_source).map(([source, count]) => (
                <div key={source} className="flex items-center justify-between">
                  <span className="text-sm text-slate-700">
                    {sourceLabel(source)}
                  </span>
                  <span className="font-display text-lg font-semibold text-slate-900">
                    {count}
                  </span>
                </div>
              ))}
              {Object.keys(kpis.ads_by_source).length === 0 && (
                <p className="text-sm text-slate-400">
                  {t("dashboard.noData")}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <div
        className="glass animate-slide-up mb-8 rounded-2xl p-6 shadow-card"
        style={{ animationDelay: "425ms" }}
      >
        <div className="mb-6 flex items-center gap-2">
          <Archive className="h-5 w-5 text-violet-600" />
          <h2 className="font-display text-xl font-semibold text-slate-900">
            {t("dashboard.adsManagement")}
          </h2>
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder={t("dashboard.searchPlaceholder")}
              value={archiveSearchTerm}
              onChange={(e) => handleArchiveSearchChange(e.target.value)}
              className="input-field w-full pl-9"
            />
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-1">
            <button
              type="button"
              onClick={() => setArchivedOnly(false)}
              aria-pressed={!showArchivedOnly}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                !showArchivedOnly
                  ? "bg-brand-600 text-white"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              <Globe className="h-3.5 w-3.5" />
              {t("dashboard.all")}
            </button>
            <button
              type="button"
              onClick={() => setArchivedOnly(true)}
              aria-pressed={showArchivedOnly}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                showArchivedOnly
                  ? "bg-violet-600 text-white"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              <ArchiveRestore className="h-3.5 w-3.5" />
              {t("dashboard.archivedOnly")}
            </button>
          </div>
        </div>

        <div className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("dashboard.governorate")}</label>
            <select
              className="input-field w-full"
              value={archiveFilters.city ?? ""}
              onChange={(e) =>
                setArchiveFilters({ ...archiveFilters, city: e.target.value || undefined })
              }
            >
              <option value="">{t("dashboard.filterAllM")}</option>
              {GOVERNORATE_NAMES.map((gov) => (
                <option key={gov} value={gov}>
                  {gov}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("dashboard.category")}</label>
            <select
              className="input-field w-full"
              value={archiveFilters.subcategory ?? ""}
              onChange={(e) => {
                const value = e.target.value;
                setArchiveFilters({
                  ...archiveFilters,
                  subcategory: value || undefined,
                  // The bedrooms filter is only shown for a specific
                  // category that has bedrooms (not "Toutes", not
                  // "Terrain"), so drop any stale value rather than leaving
                  // it silently applied while hidden.
                  bedrooms: value && value !== "land" ? archiveFilters.bedrooms : undefined,
                });
              }}
            >
              <option value="">{t("dashboard.filterAllF")}</option>
              <option value="apartment">{t("dashboard.catApartment")}</option>
              <option value="house">{t("dashboard.catHouse")}</option>
              <option value="office">{t("dashboard.catOffice")}</option>
              <option value="studio">{t("dashboard.catStudio")}</option>
              <option value="land">{t("dashboard.catLand")}</option>
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("dashboard.transaction")}</label>
            <select
              className="input-field w-full"
              value={archiveFilters.listingType ?? ""}
              onChange={(e) =>
                setArchiveFilters({ ...archiveFilters, listingType: e.target.value || undefined })
              }
            >
              <option value="">{t("dashboard.filterAllF")}</option>
              <option value="sale">{t("dashboard.forSale")}</option>
              <option value="rent">{t("dashboard.forRent")}</option>
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("dashboard.priceMin")}</label>
            <input
              type="number"
              className="input-field w-full"
              placeholder="0"
              min={0}
              value={archiveFilters.minPrice ?? ""}
              onChange={(e) =>
                setArchiveFilters({
                  ...archiveFilters,
                  minPrice: e.target.value ? Number(e.target.value) : undefined,
                })
              }
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("dashboard.priceMax")}</label>
            <input
              type="number"
              className="input-field w-full"
              placeholder="∞"
              min={0}
              value={archiveFilters.maxPrice ?? ""}
              onChange={(e) =>
                setArchiveFilters({
                  ...archiveFilters,
                  maxPrice: e.target.value ? Number(e.target.value) : undefined,
                })
              }
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">
              {t("dashboard.areaMin")}
            </label>
            <input
              type="number"
              className="input-field w-full"
              placeholder="Min"
              min={0}
              value={archiveFilters.minArea ?? ""}
              onChange={(e) =>
                setArchiveFilters({
                  ...archiveFilters,
                  minArea: e.target.value ? Number(e.target.value) : undefined,
                })
              }
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">
              {t("dashboard.areaMax")}
            </label>
            <input
              type="number"
              className="input-field w-full"
              placeholder="Max"
              min={0}
              value={archiveFilters.maxArea ?? ""}
              onChange={(e) =>
                setArchiveFilters({
                  ...archiveFilters,
                  maxArea: e.target.value ? Number(e.target.value) : undefined,
                })
              }
            />
          </div>

          {archiveFilters.subcategory && archiveFilters.subcategory !== "land" && (
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-500">
                {t("dashboard.bedroomsMin")}
              </label>
              <input
                type="number"
                className="input-field w-full"
                placeholder="Min"
                min={0}
                value={archiveFilters.bedrooms ?? ""}
                onChange={(e) =>
                  setArchiveFilters({
                    ...archiveFilters,
                    bedrooms: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
              />
            </div>
          )}
        </div>

        {Object.values(archiveFilters).some((v) => v !== undefined) && (
          <button
            type="button"
            onClick={resetArchiveFilters}
            className="mb-4 flex items-center gap-1 text-xs text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 px-2.5 py-1.5 rounded-lg"
          >
            <X className="h-3.5 w-3.5" />
            {t("dashboard.resetFilters")}
          </button>
        )}

        <div className="dt-archive overflow-x-auto rounded-xl border border-slate-100">
          <DataTable
            key={lang}
            ref={archiveTableRef}
            columns={archiveColumns}
            options={archiveTableOptions}
            onDraw={handleArchiveDraw}
            className="w-full text-left text-sm"
            slots={{
              9: (_data: unknown, row: ArchiveRow) => (
                <div className="flex justify-end">
                  <ArchiveToggle
                    archived={row.archived}
                    onToggle={() => toggleArchive(row.property)}
                  />
                </div>
              ),
            }}
          />
        </div>
      </div>

      <div
        className="glass animate-slide-up rounded-2xl p-6 shadow-card"
        style={{ animationDelay: "450ms" }}
      >
        <h2 className="mb-6 font-display text-xl font-semibold text-slate-900">
          {t("dashboard.runScrapeTitle")}
        </h2>

        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-t border-b border-slate-100 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600/10">
              <Clock className="h-4 w-4 text-brand-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-700">
                {t("dashboard.autoScrape")}
              </p>
              <p className="text-xs text-slate-400">{t("dashboard.everyMonday")}</p>
            </div>
          </div>
          <div className="flex flex-col sm:items-end">
            <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
              {t("dashboard.nextAutoScrape")}
            </span>
            <p className="font-mono text-xl font-bold text-brand-400">
              {nextScrapeTime ? formatCountdown(timeLeft) : t("dashboard.calculating")}
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
            {retraining ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("dashboard.retraining")}
              </>
            ) : scraping ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("dashboard.scrapingInProgress")} ({scrapeDuration}s)
              </>
            ) : (
              <>
                <Download className="h-4 w-4" />
                {t("dashboard.startScrape")}
              </>
            )}
          </button>

          {scraping && !retraining && (
            <button
              type="button"
              onClick={cancelScrape}
              disabled={cancelling}
              className="inline-flex items-center gap-2 rounded-xl bg-red-500/10 px-4 py-2.5 text-sm font-medium text-red-600 transition hover:bg-red-500/20 disabled:opacity-50"
            >
              {cancelling ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t("dashboard.stopping")}
                </>
              ) : (
                <>
                  <Ban className="h-4 w-4" />
                  {t("dashboard.stopScrape")}
                </>
              )}
            </button>
          )}
        </div>

        {scrapeError && (
          <p className="mt-4 text-sm text-red-600">{scrapeError}</p>
        )}

        {scrapeCancelled && !scraping && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-amber-500/10 px-4 py-3 text-sm text-amber-600">
            <Ban className="h-4 w-4 shrink-0" />
            {t("dashboard.scrapeCancelledMsg")}
          </div>
        )}

        {scraping && scrapeProgress && (
          <div className="mt-6 rounded-xl border border-slate-100 bg-slate-50 p-4">
            <h4 className="mb-3 text-sm font-semibold text-slate-900">
              {t("dashboard.scrapeProgress")}
            </h4>
            <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
              <span>{t("dashboard.sourcesCompleted")}</span>
              <span>
                {scrapeProgress.completed_sources}/
                {scrapeProgress.total_sources}
              </span>
            </div>
            <div className="space-y-2">
              {Object.entries(scrapeProgress.sources).map(
                ([source, progress]) => (
                  <div
                    key={source}
                    className="rounded-lg bg-slate-100 px-3 py-2"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div
                          className={`h-2 w-2 rounded-full ${
                            progress.status === "completed"
                              ? "bg-emerald-500"
                              : progress.status === "running"
                                ? "bg-brand-400 animate-pulse"
                                : progress.status === "error"
                                  ? "bg-red-500"
                                  : progress.status === "cancelled"
                                    ? "bg-amber-500"
                                    : "bg-slate-300"
                          }`}
                        />
                        <span className="text-xs font-medium text-slate-700">
                          {sourceLabel(source)}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-slate-500">
                        {progress.status === "running" && progress.phase && (
                          <span className="text-brand-400">
                            {t("dashboard.phase")} {phaseLabel(progress.phase)}
                            {progress.step
                              ? ` — ${stepLabel(progress.step)}`
                              : ""}
                            {progress.step === "enriching" &&
                            progress.total_pages > 0
                              ? ` ${progress.pages_processed}/${progress.total_pages}`
                              : progress.step === "listing"
                                ? ` (${progress.pages_processed} ${t("dashboard.pagesSuffix")})`
                                : ""}
                          </span>
                        )}
                        {progress.status === "completed" && (
                          <span className="text-emerald-600">{t("dashboard.done")}</span>
                        )}
                        {progress.status === "error" && (
                          <span className="text-red-600">{t("dashboard.error")}</span>
                        )}
                        {progress.status === "cancelled" && (
                          <span className="text-amber-600">{t("dashboard.cancelled")}</span>
                        )}
                        {progress.status === "pending" && (
                          <span className="text-slate-400">{t("dashboard.pending")}</span>
                        )}
                      </div>
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2">
                      {PHASE_ORDER.map((phase) => {
                        const stats = progress.phases?.[phase];
                        const phaseStatus = stats?.status ?? "pending";
                        return (
                          <div
                            key={phase}
                            className={`rounded-md px-2 py-1 text-[11px] ${
                              phaseStatus === "completed"
                                ? "bg-emerald-500/10 text-emerald-600"
                                : phaseStatus === "running"
                                  ? "bg-brand-500/10 text-brand-400"
                                  : "bg-slate-50 text-slate-400"
                            }`}
                          >
                            <span className="font-medium">
                              {phaseLabel(phase)}
                            </span>
                            {phaseStatus === "completed" && stats && (
                              <span className="ml-1">
                                {stats.count} · +{stats.inserted}
                              </span>
                            )}
                            {phaseStatus === "running" && (
                              <span className="ml-1">{t("dashboard.running")}</span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ),
              )}
            </div>
          </div>
        )}

        {scrapeResults && (
          <div className="mt-6 overflow-x-auto rounded-xl border border-slate-100">
            {scrapeDuration > 0 && (
              <div className="bg-slate-50 px-4 py-3 text-sm text-slate-700 font-medium border-b border-slate-100">
                {t("dashboard.completedIn").replace("{n}", String(scrapeDuration))}
              </div>
            )}
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50 text-xs text-slate-400">
                  <th className="px-4 py-3 font-medium">{t("dashboard.colSource")}</th>
                  <th className="px-4 py-3 font-medium">{t("dashboard.phase")}</th>
                  <th className="px-4 py-3 font-medium">{t("dashboard.found")}</th>
                  <th className="px-4 py-3 font-medium">{t("dashboard.inserted")}</th>
                  <th className="px-4 py-3 font-medium">{t("dashboard.alreadyInDb")}</th>
                  <th className="px-4 py-3 font-medium">{t("dashboard.errors")}</th>
                  <th className="px-4 py-3 font-medium">{t("dashboard.archived")}</th>
                </tr>
              </thead>
              <tbody>
                {scrapeResults.map((result) => {
                  const sourceKey = result.source.replace("scrape_", "");
                  if (result.error) {
                    return (
                      <tr
                        key={result.source}
                        className="border-b border-slate-100 last:border-0"
                      >
                        <td className="px-4 py-3 font-medium text-slate-900">
                          {sourceLabel(sourceKey)}
                        </td>
                        <td colSpan={6} className="px-4 py-3 text-red-600">
                          {result.error}
                        </td>
                      </tr>
                    );
                  }
                  // Grand-total summary row across every source.
                  if (result.source === "total") {
                    return (
                      <tr
                        key={result.source}
                        className="border-t-2 border-slate-200 bg-slate-50 font-semibold last:border-b-0"
                      >
                        <td className="px-4 py-3 text-slate-900">{t("dashboard.total")}</td>
                        <td className="px-4 py-3" />
                        <td className="px-4 py-3 text-slate-800">
                          {result.count ?? 0}
                        </td>
                        <td className="px-4 py-3 text-emerald-600">
                          {result.inserted ?? 0}
                        </td>
                        <td className="px-4 py-3 text-slate-700">
                          {result.skipped ?? 0}
                        </td>
                        <td className="px-4 py-3 text-amber-600">
                          {result.errors ?? 0}
                        </td>
                        <td className="px-4 py-3 text-violet-600">
                          {result.archived ?? 0}
                        </td>
                      </tr>
                    );
                  }
                  const phaseRows = result.phases
                    ? PHASE_ORDER.filter((phase) => result.phases?.[phase]).map(
                        (phase) => {
                          const stats = result.phases![phase];
                          return (
                            <tr
                              key={`${result.source}-${phase}`}
                              className="border-b border-slate-100 bg-slate-50 text-xs"
                            >
                              <td className="px-4 py-2" />
                              <td className="px-4 py-2 text-slate-500">
                                {phaseLabel(phase)}
                              </td>
                              <td className="px-4 py-2 text-slate-500">
                                {stats.count}
                              </td>
                              <td className="px-4 py-2 text-emerald-600/80">
                                {stats.inserted}
                              </td>
                              <td className="px-4 py-2 text-slate-400">
                                {stats.skipped}
                              </td>
                              <td className="px-4 py-2 text-amber-600/80">
                                {stats.errors}
                              </td>
                              <td className="px-4 py-2" />
                            </tr>
                          );
                        },
                      )
                    : [];
                  return (
                    <Fragment key={result.source}>
                      <tr className="border-b border-slate-100">
                        <td className="px-4 py-3 font-medium text-slate-900">
                          {sourceLabel(sourceKey)}
                        </td>
                        <td className="px-4 py-3 text-slate-400">{t("dashboard.total")}</td>
                        <td className="px-4 py-3 text-slate-700">
                          {result.count}
                        </td>
                        <td className="px-4 py-3 text-emerald-600">
                          {result.inserted}
                        </td>
                        <td className="px-4 py-3 text-slate-500">
                          {result.skipped}
                        </td>
                        <td className="px-4 py-3 text-amber-600">
                          {result.errors}
                        </td>
                        <td className="px-4 py-3 text-violet-600">
                          {result.archived || 0}
                        </td>
                      </tr>
                      {phaseRows}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            <p className="border-t border-slate-100 px-4 py-3 text-xs text-slate-400">
              {t("dashboard.alreadyInDbNote")}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
