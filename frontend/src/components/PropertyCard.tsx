import { Link } from "react-router-dom";
import { ArrowUpRight, BedDouble, MapPin, Maximize2 } from "lucide-react";
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
}

export function PropertyCard({ property, index = 0 }: PropertyCardProps) {
  const { t } = useLang();
  const gradient = propertyGradient(property.id);
  const mainImage = property.images && property.images.length > 0 ? property.images[0] : null;

  return (
    <div className="group block animate-slide-up overflow-hidden rounded-2xl border border-brand-200 bg-white shadow-card transition hover:-translate-y-1 hover:border-brand-500/30 hover:shadow-glow"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <Link to={`/property/${property.id}`} className="block">
        <div className="relative h-44 w-full overflow-hidden bg-slate-100">
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
            <span className="rounded-lg bg-white/85 px-2.5 py-1 text-xs font-medium text-slate-900 backdrop-blur">
              {sourceLabel(property.source)}
            </span>
            <span className="rounded-lg bg-white/85 px-2.5 py-1 text-xs font-medium text-slate-700 backdrop-blur">
              {subcategoryLabel(property.subcategory, property.property_type)}
            </span>
            <span className="rounded-lg bg-white/85 px-2.5 py-1 text-xs font-medium text-amber-700 backdrop-blur">
              {listingTypeLabel(property.listing_type)}
            </span>
          </div>
          <div className="absolute bottom-4 left-4 right-4">
            <p className="font-display text-2xl font-semibold text-white drop-shadow">
              {formatPrice(property.price)}
            </p>
          </div>
        </div>

        <div className="p-5">
          <h3 className="mb-2 line-clamp-2 font-semibold leading-snug text-slate-900 group-hover:text-slate-900">
            {property.title}
          </h3>

          <div className="mb-3 flex items-center gap-1.5 text-sm text-slate-500">
            <MapPin className="h-3.5 w-3.5 shrink-0 text-brand-500" />
            <span className="truncate">{governorateOf(property)}</span>
          </div>

          {property.description && (
            <p className="mb-4 line-clamp-2 text-sm text-slate-400">
              {truncate(property.description, 100)}
            </p>
          )}

          <div className="mb-4 flex flex-wrap gap-3 text-xs text-slate-500">
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

          <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-4">
            <span className="text-sm font-medium text-brand-400 transition group-hover:text-slate-900">
              {t("card.viewDetails")}
            </span>
            <ArrowUpRight className="h-4 w-4 text-slate-400 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-slate-900" />
          </div>
        </div>
      </Link>
    </div>
  );
}
