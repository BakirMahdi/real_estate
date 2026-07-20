import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heart } from "lucide-react";
import { api } from "../api/client";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { PropertyCard } from "../components/PropertyCard";
import type { Property } from "../types/property";
import { useLang } from "../lib/i18n";

export function FavoritesPage() {
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { t } = useLang();

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .getFavorites()
      .then((data) => setProperties(data.items))
      .catch((err) => setError(err instanceof Error ? err.message : t("favorites.loadError")))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  // Every card on this page is, by definition, a favorite - so unfavoriting
  // one should drop it from the grid immediately instead of leaving a
  // now-unfavorited card sitting here until the next reload.
  const handleFavoriteChange = (propertyId: number, isFavorite: boolean) => {
    if (!isFavorite) {
      setProperties((prev) => prev.filter((p) => p.id !== propertyId));
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <section className="mb-10 animate-fade-in">
        <div className="mb-2 flex items-center gap-2 text-sm text-brand-400">
          <Heart className="h-4 w-4" />
          {t("favorites.eyebrow")}
        </div>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-slate-900 sm:text-5xl">
          {t("favorites.title")}
        </h1>
        <p className="mt-3 max-w-2xl text-slate-500">{t("favorites.subtitle")}</p>
      </section>

      {loading ? (
        <LoadingSpinner label={t("favorites.loading")} />
      ) : error ? (
        <div className="glass rounded-2xl p-8 text-center">
          <p className="text-red-600">{error}</p>
          <button type="button" onClick={load} className="btn-primary mt-4">
            {t("home.retry")}
          </button>
        </div>
      ) : properties.length === 0 ? (
        <div className="glass rounded-2xl p-12 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand-500/20">
            <Heart className="h-6 w-6 text-brand-400" />
          </div>
          <p className="mb-6 text-slate-500">{t("favorites.empty")}</p>
          <Link to="/annonces" className="btn-primary inline-flex">
            {t("favorites.browse")}
          </Link>
        </div>
      ) : (
        <>
          <p className="mb-6 text-sm text-slate-500">
            <span className="font-medium text-slate-900">{properties.length}</span>{" "}
            {properties.length !== 1 ? t("favorites.count.many") : t("favorites.count.one")}
          </p>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {properties.map((property, index) => (
              <PropertyCard
                key={property.id}
                property={property}
                index={index}
                onFavoriteChange={handleFavoriteChange}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
