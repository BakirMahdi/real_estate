import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowUpRight, BedDouble, Heart, MapPin, Maximize2 } from "lucide-react";
import { api, isAuthenticated } from "../api/client";
import type { Property } from "../types/property";
import {
  formatArea,
  formatPrice,
  governorateOf,
  listingTypeLabel,
  propertyGradient,
  sourceLabel,
  subcategoryLabel,
  truncate,
} from "../lib/format";
import { useLang } from "../lib/i18n";

interface PropertyCardProps {
  property: Property;
  index?: number;
  /** Called after a successful toggle - e.g. the favorites page uses this to
   * drop the card from its list the moment it's unfavorited. */
  onFavoriteChange?: (propertyId: number, isFavorite: boolean) => void;
}

export function PropertyCard({ property, index = 0, onFavoriteChange }: PropertyCardProps) {
  const { t } = useLang();
  const navigate = useNavigate();
  const gradient = propertyGradient(property.id);
  const mainImage = property.images && property.images.length > 0 ? property.images[0] : null;
  // Seeded from the list response (see get_properties' favorites join on the
  // backend) so cards show the right state on first render, no per-card
  // fetch needed - then updated locally as the user toggles it.
  const [isFavorite, setIsFavorite] = useState(property.is_favorite ?? false);
  const [favoriteLoading, setFavoriteLoading] = useState(false);

  const toggleFavorite = async (e: React.MouseEvent) => {
    // The button lives inside the card's <Link> - without these, a click
    // would also navigate to the property page.
    e.preventDefault();
    e.stopPropagation();

    if (!isAuthenticated()) {
      navigate(`/login?next=/property/${property.id}`);
      return;
    }
    if (favoriteLoading) return;

    const next = !isFavorite;
    setFavoriteLoading(true);
    setIsFavorite(next); // optimistic; reverted below on failure
    try {
      if (next) {
        await api.addFavorite(property.id);
      } else {
        await api.removeFavorite(property.id);
      }
      onFavoriteChange?.(property.id, next);
    } catch {
      setIsFavorite(!next);
    } finally {
      setFavoriteLoading(false);
    }
  };

  return (
    <div className="group block animate-slide-up overflow-hidden rounded-[20px] border border-gray-200 dark:border-white/10 bg-white dark:bg-navy-800 shadow-card transition hover:-translate-y-1 hover:border-brand-500/30 hover:shadow-glow"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <Link to={`/property/${property.id}`} className="block">
        <div className="relative h-44 w-full overflow-hidden bg-lightPrimary dark:bg-navy-700">
          {mainImage ? (
            <img
              src={mainImage}
              alt={property.title}
              className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
              loading="lazy"
            />
          ) : (
            <div className={`absolute inset-0 bg-gradient-to-br ${gradient}`}>
              <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGRlZnM+PHBhdHRlcm4gaWQ9ImEiIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCIgcGF0dGVyblVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHBhdGggZD0iTTAgMTBoMTBNMTAgMHYxMCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJyZ2JhKDI1NSwyNTUsMjU1LDAuMDUpIi8+PC9wYXR0ZXJuPjwvZGVmcz48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSJ1cmwoI2EpIi8+PC9zdmc+')] opacity-50" />
            </div>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-black/10" />
          <div className="absolute left-4 top-4 flex gap-2">
            <span className="rounded-lg bg-white/85 dark:bg-navy-800/85 px-2.5 py-1 text-xs font-medium text-navy-700 dark:text-white backdrop-blur">
              {sourceLabel(property.source)}
            </span>
            <span className="rounded-lg bg-white/85 dark:bg-navy-800/85 px-2.5 py-1 text-xs font-medium text-navy-700 dark:text-gray-300 backdrop-blur">
              {subcategoryLabel(property.subcategory, property.property_type)}
            </span>
            <span className="rounded-lg bg-white/85 dark:bg-navy-800/85 px-2.5 py-1 text-xs font-medium text-horizonOrange-600 dark:text-horizonOrange-500 backdrop-blur">
              {listingTypeLabel(property.listing_type)}
            </span>
          </div>

          <button
            type="button"
            onClick={toggleFavorite}
            disabled={favoriteLoading}
            aria-pressed={isFavorite}
            aria-label={isFavorite ? t("prop.removeFavorite") : t("prop.addFavorite")}
            title={isFavorite ? t("prop.removeFavorite") : t("prop.addFavorite")}
            className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-full border border-gray-200 dark:border-white/10 bg-white/85 dark:bg-navy-800/85 text-navy-700 dark:text-gray-300 backdrop-blur transition hover:bg-white dark:hover:bg-navy-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Heart className={`h-4 w-4 transition ${isFavorite ? "fill-horizonRed-500 text-horizonRed-500 dark:fill-horizonRed-400 dark:text-horizonRed-400" : ""}`} />
          </button>

          <div className="absolute bottom-4 left-4 right-4">
            <p className="font-display text-2xl font-semibold text-white drop-shadow">
              {formatPrice(property.price)}
            </p>
          </div>
        </div>

        <div className="p-5">
          <h3 className="mb-2 line-clamp-2 font-semibold leading-snug text-navy-700 transition group-hover:text-brand-500 dark:text-white dark:group-hover:text-brand-200">
            {property.title}
          </h3>

          <div className="mb-3 flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-600">
            <MapPin className="h-3.5 w-3.5 shrink-0 text-brand-500" />
            <span className="truncate">{governorateOf(property)}</span>
          </div>

          {property.description && (
            <p className="mb-4 line-clamp-2 text-sm text-gray-700 dark:text-gray-600">
              {truncate(property.description, 100)}
            </p>
          )}

          <div className="mb-4 flex flex-wrap gap-3 text-xs text-gray-700 dark:text-gray-600">
            <span className="flex items-center gap-1">
              <Maximize2 className="h-3.5 w-3.5" />
              {formatArea(property.area)}
            </span>
            {property.bedrooms != null && property.property_type === "house" && (
              <span className="flex items-center gap-1">
                <BedDouble className="h-3.5 w-3.5" />
                {property.bedrooms} {t("card.bedroomsAbbr")}
              </span>
            )}
          </div>

          <div className="flex items-center justify-between gap-3 border-t border-gray-200 dark:border-white/10 pt-4">
            <span className="text-sm font-medium text-brand-500 dark:text-brand-400 transition group-hover:text-navy-700 dark:group-hover:text-white">
              {t("card.viewDetails")}
            </span>
            <ArrowUpRight className="h-4 w-4 text-gray-700 dark:text-gray-600 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-navy-700 dark:group-hover:text-white" />
          </div>
        </div>
      </Link>
    </div>
  );
}
