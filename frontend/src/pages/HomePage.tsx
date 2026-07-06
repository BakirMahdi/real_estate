import { useCallback, useEffect, useMemo, useState } from "react";
import { Home, RefreshCw } from "lucide-react";
import { api } from "../api/client";
import { FilterBar } from "../components/FilterBar";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PropertyCard } from "../components/PropertyCard";
import type { Property, SearchFilters } from "../types/property";

const PAGE_SIZE = 24;

const defaultFilters: SearchFilters = {
  limit: PAGE_SIZE,
  offset: 0,
};

export function HomePage() {
  const [properties, setProperties] = useState<Property[]>([]);
  const [cities, setCities] = useState<string[]>([]);
  const [filters, setFilters] = useState<SearchFilters>(defaultFilters);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCities = useCallback(async () => {
    try {
      const data = await api.getAllProperties();
      const unique = [
        ...new Set(
          data.items.map((p) => p.city).filter((c): c is string => Boolean(c)),
        ),
      ].sort();
      setCities(unique);
    } catch {
      /* cities are optional for filters */
    }
  }, []);

  const loadProperties = useCallback(
    async (activeFilters: SearchFilters, append = false) => {
      append ? setLoadingMore(true) : setLoading(true);
      setError(null);

      try {
        const data = await api.searchProperties(activeFilters);
        setTotal(data.count);
        setProperties((prev) => (append ? [...prev, ...data.items] : data.items));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Erreur de chargement");
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [],
  );

  useEffect(() => {
    loadCities();
  }, [loadCities]);

  useEffect(() => {
    const append = (filters.offset ?? 0) > 0;
    loadProperties(filters, append);
  }, [filters, loadProperties]);

  const hasMore = useMemo(
    () => properties.length < total,
    [properties.length, total],
  );

  const loadMore = () => {
    const next = { ...filters, offset: (filters.offset ?? 0) + PAGE_SIZE };
    setFilters(next);
  };

  const resetFilters = () => setFilters(defaultFilters);

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
          Annonces immobilières agrégées depuis Tayara et Mubawab — maisons,
          appartements et terrains à travers la Tunisie.
        </p>
      </section>

      <div className="mb-8">
        <FilterBar
          filters={filters}
          cities={cities}
          onChange={setFilters}
          onReset={resetFilters}
        />
      </div>

      <div className="mb-6 flex items-center justify-between">
        <p className="text-sm text-slate-400">
          <span className="font-medium text-white">{total}</span> annonce
          {total !== 1 ? "s" : ""} trouvée{total !== 1 ? "s" : ""}
        </p>
        <button
          type="button"
          onClick={() => loadProperties(filters)}
          className="btn-secondary py-2 text-xs"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Actualiser
        </button>
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

          {hasMore && (
            <div className="mt-10 flex justify-center">
              <button
                type="button"
                onClick={loadMore}
                disabled={loadingMore}
                className="btn-secondary"
              >
                {loadingMore ? "Chargement..." : "Charger plus"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
