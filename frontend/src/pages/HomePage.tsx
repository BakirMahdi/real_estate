import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Home } from "lucide-react";
import { api } from "../api/client";
import { governorateOf, GOVERNORATE_NAMES } from "../lib/format";
import { FilterBar } from "../components/FilterBar";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PropertyCard } from "../components/PropertyCard";
import type { Property, SearchFilters } from "../types/property";
import { useLang } from "../lib/i18n";

const PAGE_SIZE = 12;

// The active search lives in the URL query string, not component state, so
// leaving for a property page and pressing "retour" restores the exact search
// and page (browser back re-reads these params) instead of resetting to page 1
// with no filters. It also makes a given search shareable/bookmarkable.
const STRING_KEYS = ["city", "property_type", "listing_type", "query", "subcategory"] as const;
const NUMERIC_KEYS = ["min_price", "max_price", "min_area", "max_area", "bedrooms"] as const;

function filtersFromParams(params: URLSearchParams): SearchFilters {
  const filters: SearchFilters = { limit: PAGE_SIZE, offset: 0 };
  for (const key of STRING_KEYS) {
    const value = params.get(key);
    if (value) filters[key] = value;
  }
  for (const key of NUMERIC_KEYS) {
    const value = params.get(key);
    if (value && !Number.isNaN(Number(value))) filters[key] = Number(value);
  }
  // Pages are 1-based in the URL for readability; page 1 (the default) is
  // omitted so a fresh search stays at a clean `/annonces`.
  const page = Number(params.get("page"));
  if (Number.isFinite(page) && page > 1) filters.offset = (page - 1) * PAGE_SIZE;
  return filters;
}

function paramsFromFilters(filters: SearchFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of STRING_KEYS) {
    if (filters[key]) params.set(key, String(filters[key]));
  }
  for (const key of NUMERIC_KEYS) {
    if (filters[key] != null) params.set(key, String(filters[key]));
  }
  const page = Math.floor((filters.offset ?? 0) / PAGE_SIZE) + 1;
  if (page > 1) params.set("page", String(page));
  return params;
}

export function HomePage() {
  const [properties, setProperties] = useState<Property[]>([]);
  const [governorates, setGovernorates] = useState<string[]>([]);
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => filtersFromParams(searchParams), [searchParams]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { t } = useLang();

  // `replace` (not push) so typing in the search box or paging doesn't stack a
  // history entry per keystroke; the listings page stays a single entry that
  // always reflects the current search, and returning from a property page
  // lands right back on it.
  const applyFilters = useCallback(
    (next: SearchFilters) => setSearchParams(paramsFromFilters(next), { replace: true }),
    [setSearchParams],
  );

  const loadGovernorates = useCallback(async () => {
    try {
      const data = await api.getAllProperties(true);
      const present = new Set(data.items.map((p) => governorateOf(p)));
      // Only show real governorates in the dropdown — never leak the raw
      // address of the few rows that can't be resolved.
      const unique = GOVERNORATE_NAMES.filter((g) => present.has(g)).sort(
        (a, b) => a.localeCompare(b, "fr"),
      );
      setGovernorates(unique);
    } catch {
      /* governorates are optional for filters */
    }
  }, []);

  const loadProperties = useCallback(async (activeFilters: SearchFilters) => {
    setLoading(true);
    setError(null);

    try {
      const data = await api.searchProperties(activeFilters);
      setTotal(data.count);
      setProperties(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("home.loadError"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGovernorates();
  }, [loadGovernorates]);

  useEffect(() => {
    loadProperties(filters);
  }, [filters, loadProperties]);

  const resetFilters = () => setSearchParams(new URLSearchParams(), { replace: true });

  const currentPage = Math.floor((filters.offset ?? 0) / PAGE_SIZE) + 1;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const goToPage = (page: number) => {
    applyFilters({ ...filters, offset: (page - 1) * PAGE_SIZE });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const pages = useMemo(() => {
    const list: (number | string)[] = [];
    const maxVisible = 5;

    if (totalPages <= maxVisible) {
      for (let i = 1; i <= totalPages; i++) list.push(i);
    } else {
      list.push(1);

      const start = Math.max(2, currentPage - 1);
      const end = Math.min(totalPages - 1, currentPage + 1);

      if (start > 2) {
        list.push("...");
      }

      for (let i = start; i <= end; i++) {
        list.push(i);
      }

      if (end < totalPages - 1) {
        list.push("...");
      }

      list.push(totalPages);
    }
    return list;
  }, [currentPage, totalPages]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <section className="mb-10 animate-fade-in">
        <div className="mb-2 flex items-center gap-2 text-sm text-brand-500 dark:text-brand-400">
          <Home className="h-4 w-4" />
          {t("home.catalog")}
        </div>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-navy-700 dark:text-white sm:text-5xl">
          {t("home.title")}
        </h1>
        <p className="mt-3 max-w-2xl text-gray-700 dark:text-gray-600">{t("home.subtitle")}</p>
      </section>

      <div className="mb-8">
        <FilterBar
          filters={filters}
          governorates={governorates}
          onChange={applyFilters}
          onReset={resetFilters}
        />
      </div>

      <div className="mb-6 flex items-center justify-between">
        <p className="text-sm text-gray-700 dark:text-gray-600">
          <span className="font-medium text-navy-700 dark:text-white">{total}</span>{" "}
          {total !== 1 ? t("home.found.many") : t("home.found.one")}
        </p>
      </div>

      {loading ? (
        <LoadingSpinner label={t("home.loading")} />
      ) : error ? (
        <div className="glass p-8 text-center">
          <p className="text-horizonRed-500 dark:text-horizonRed-400">{error}</p>
          <button
            type="button"
            onClick={() => loadProperties(filters)}
            className="btn-primary mt-4"
          >
            {t("home.retry")}
          </button>
        </div>
      ) : properties.length === 0 ? (
        <div className="glass p-12 text-center">
          <p className="text-gray-700 dark:text-gray-600">{t("home.noResults")}</p>
        </div>
      ) : (
        <>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {properties.map((property, index) => (
              <PropertyCard
                key={property.id}
                property={property}
                index={index}
              />
            ))}
          </div>

          {/* Pagination system */}
          {totalPages > 1 && (
            <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-gray-200 dark:border-white/10 pt-6 sm:flex-row animate-fade-in">
              <p className="text-sm text-gray-700 dark:text-gray-600">
                {t("home.showing")}{" "}
                <span className="font-medium text-navy-700 dark:text-white">
                  {Math.min((filters.offset ?? 0) + 1, total)}
                </span>{" "}
                {t("home.to")}{" "}
                <span className="font-medium text-navy-700 dark:text-white">
                  {Math.min((filters.offset ?? 0) + properties.length, total)}
                </span>{" "}
                {t("home.of")} <span className="font-medium text-navy-700 dark:text-white">{total}</span>{" "}
                {t("home.listings")}
              </p>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => goToPage(currentPage - 1)}
                  disabled={currentPage === 1 || loading}
                  className="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-navy-800 text-gray-700 dark:text-gray-600 transition hover:bg-lightPrimary dark:hover:bg-navy-700 hover:text-navy-700 dark:hover:text-white disabled:pointer-events-none disabled:opacity-30"
                  aria-label={t("home.prevPage")}
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>

                {pages.map((p, idx) => {
                  if (typeof p === "string") {
                    return (
                      <span
                        key={`ell-${idx}`}
                        className="flex h-9 w-9 items-center justify-center text-sm text-gray-700 dark:text-gray-600"
                      >
                        {p}
                      </span>
                    );
                  }

                  const isActive = p === currentPage;
                  return (
                    <button
                      key={`page-${p}`}
                      type="button"
                      onClick={() => goToPage(p)}
                      disabled={loading}
                      className={`flex h-9 w-9 items-center justify-center rounded-lg text-sm font-medium transition ${
                        isActive
                          ? "bg-brand-500 text-white shadow-md"
                          : "border border-gray-200 dark:border-white/10 bg-white dark:bg-navy-800 text-gray-700 dark:text-gray-600 hover:bg-lightPrimary dark:hover:bg-navy-700 hover:text-navy-700 dark:hover:text-white"
                      }`}
                    >
                      {p}
                    </button>
                  );
                })}

                <button
                  type="button"
                  onClick={() => goToPage(currentPage + 1)}
                  disabled={currentPage === totalPages || loading}
                  className="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-navy-800 text-gray-700 dark:text-gray-600 transition hover:bg-lightPrimary dark:hover:bg-navy-700 hover:text-navy-700 dark:hover:text-white disabled:pointer-events-none disabled:opacity-30"
                  aria-label={t("home.nextPage")}
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
