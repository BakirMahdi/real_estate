import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Home } from "lucide-react";
import { api } from "../api/client";
import { governorateOf, GOVERNORATE_NAMES } from "../lib/format";
import { FilterBar } from "../components/FilterBar";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PropertyCard } from "../components/PropertyCard";
import type { Property, SearchFilters } from "../types/property";

const PAGE_SIZE = 12;

const defaultFilters: SearchFilters = {
  limit: PAGE_SIZE,
  offset: 0,
};

export function HomePage() {
  const [properties, setProperties] = useState<Property[]>([]);
  const [governorates, setGovernorates] = useState<string[]>([]);
  const [filters, setFilters] = useState<SearchFilters>(defaultFilters);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
      setError(err instanceof Error ? err.message : "Erreur de chargement");
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

  const resetFilters = () => setFilters(defaultFilters);

  const currentPage = Math.floor((filters.offset ?? 0) / PAGE_SIZE) + 1;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const goToPage = (page: number) => {
    const next = { ...filters, offset: (page - 1) * PAGE_SIZE };
    setFilters(next);
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
        <div className="mb-2 flex items-center gap-2 text-sm text-brand-400">
          <Home className="h-4 w-4" />
          Catalogue
        </div>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-white sm:text-5xl">
          Trouvez votre bien
        </h1>
        <p className="mt-3 max-w-2xl text-slate-400">
          Annonces immobilières agrégées depuis Tayara, Mubawab et Expat —
          maisons, appartements et terrains à travers la Tunisie.
        </p>
      </section>

      <div className="mb-8">
        <FilterBar
          filters={filters}
          governorates={governorates}
          onChange={setFilters}
          onReset={resetFilters}
        />
      </div>

      <div className="mb-6 flex items-center justify-between">
        <p className="text-sm text-slate-400">
          <span className="font-medium text-white">{total}</span> annonce
          {total !== 1 ? "s" : ""} trouvée{total !== 1 ? "s" : ""}
        </p>
      </div>

      {loading ? (
        <LoadingSpinner label="Chargement des annonces..." />
      ) : error ? (
        <div className="glass rounded-2xl p-8 text-center">
          <p className="text-red-400">{error}</p>
          <button
            type="button"
            onClick={() => loadProperties(filters)}
            className="btn-primary mt-4"
          >
            Réessayer
          </button>
        </div>
      ) : properties.length === 0 ? (
        <div className="glass rounded-2xl p-12 text-center">
          <p className="text-slate-400">Aucune annonce ne correspond à vos filtres.</p>
        </div>
      ) : (
        <>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {properties.map((property, index) => (
              <PropertyCard key={property.id} property={property} index={index} />
            ))}
          </div>

          {/* Pagination system */}
          {totalPages > 1 && (
            <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-white/5 pt-6 sm:flex-row animate-fade-in">
              <p className="text-sm text-slate-400">
                Affichage de <span className="font-medium text-white">{Math.min((filters.offset ?? 0) + 1, total)}</span> à{" "}
                <span className="font-medium text-white">
                  {Math.min((filters.offset ?? 0) + properties.length, total)}
                </span>{" "}
                sur <span className="font-medium text-white">{total}</span> annonces
              </p>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => goToPage(currentPage - 1)}
                  disabled={currentPage === 1 || loading}
                  className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 bg-slate-900/40 text-slate-400 transition hover:bg-slate-800 hover:text-white disabled:pointer-events-none disabled:opacity-30"
                  aria-label="Page précédente"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>

                {pages.map((p, idx) => {
                  if (typeof p === "string") {
                    return (
                      <span
                        key={`ell-${idx}`}
                        className="flex h-9 w-9 items-center justify-center text-sm text-slate-500"
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
                          ? "bg-gradient-to-r from-brand-600 to-brand-500 text-white shadow-lg shadow-brand-600/20"
                          : "border border-white/10 bg-slate-900/40 text-slate-400 hover:bg-slate-800 hover:text-white"
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
                  className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 bg-slate-900/40 text-slate-400 transition hover:bg-slate-800 hover:text-white disabled:pointer-events-none disabled:opacity-30"
                  aria-label="Page suivante"
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
