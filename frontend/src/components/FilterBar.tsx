import { Search, SlidersHorizontal, X } from "lucide-react";
import type { SearchFilters } from "../types/property";
import { useLang } from "../lib/i18n";

interface FilterBarProps {
  filters: SearchFilters;
  governorates: string[];
  onChange: (filters: SearchFilters) => void;
  onReset: () => void;
}

export function FilterBar({ filters, governorates, onChange, onReset }: FilterBarProps) {
  const { t } = useLang();
  const set = (key: keyof SearchFilters, value: any) => {
    onChange({
      ...filters,
      [key]: value === "" ? undefined : value,
      offset: 0,
    });
  };

  const hasFilters = Object.entries(filters).some(
    ([key, value]) => key !== "limit" && key !== "offset" && value !== undefined && value !== "",
  );

  return (
    <div className="glass animate-fade-in rounded-2xl p-5 shadow-card space-y-4">
      {/* Top Section: Search Input and Actions */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-slate-100 pb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            className="input-field pl-10 pr-4 py-2.5 w-full bg-white border-brand-200 text-slate-900 placeholder-slate-400 rounded-xl focus:border-brand-500/50 focus:ring-1 focus:ring-brand-500/30"
            placeholder={t("filter.search")}
            value={filters.query ?? ""}
            onChange={(e) => set("query", e.target.value)}
          />
        </div>
        <div className="flex items-center justify-between gap-4 shrink-0">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
            <SlidersHorizontal className="h-4 w-4 text-brand-400" />
            {t("filter.filters")}
          </div>
          {hasFilters && (
            <button
              type="button"
              onClick={onReset}
              className="flex items-center gap-1 text-xs text-slate-400 transition hover:text-slate-600 hover:bg-slate-100 px-2.5 py-1.5 rounded-lg"
            >
              <X className="h-3.5 w-3.5" />
              {t("filter.reset")}
            </button>
          )}
        </div>
      </div>

      {/* Filters Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("filter.governorate")}</label>
          <select
            className="input-field w-full"
            value={filters.city ?? ""}
            onChange={(e) => set("city", e.target.value)}
          >
            <option value="">{t("filter.all")}</option>
            {governorates.map((gov) => (
              <option key={gov} value={gov}>
                {gov}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("filter.category")}</label>
          <select
            className="input-field w-full"
            value={filters.subcategory ?? ""}
            onChange={(e) => {
              const value = e.target.value;
              onChange({
                ...filters,
                subcategory: value === "" ? undefined : value,
                // The bedrooms filter is only shown for a specific category
                // that has bedrooms (not "Toutes", not "Terrain"), so drop
                // any stale value rather than leaving it silently applied
                // while hidden.
                bedrooms: value && value !== "land" ? filters.bedrooms : undefined,
                offset: 0,
              });
            }}
          >
            <option value="">{t("filter.allF")}</option>
            <option value="apartment">{t("cat.apartment")}</option>
            <option value="house">{t("cat.house")}</option>
            <option value="office">{t("cat.office")}</option>
            <option value="studio">{t("cat.studio")}</option>
            <option value="land">{t("cat.land")}</option>
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("filter.transaction")}</label>
          <select
            className="input-field w-full"
            value={filters.listing_type ?? ""}
            onChange={(e) => set("listing_type", e.target.value)}
          >
            <option value="">{t("filter.allF")}</option>
            <option value="sale">{t("listing.sale")}</option>
            <option value="rent">{t("listing.rent")}</option>
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("filter.minPrice")}</label>
          <input
            type="number"
            className="input-field w-full"
            placeholder="0"
            min={0}
            value={filters.min_price ?? ""}
            onChange={(e) => set("min_price", e.target.value ? Number(e.target.value) : undefined)}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("filter.maxPrice")}</label>
          <input
            type="number"
            className="input-field w-full"
            placeholder="∞"
            min={0}
            value={filters.max_price ?? ""}
            onChange={(e) => set("max_price", e.target.value ? Number(e.target.value) : undefined)}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("filter.minArea")}</label>
          <input
            type="number"
            className="input-field w-full"
            placeholder="Min"
            min={0}
            value={filters.min_area ?? ""}
            onChange={(e) => set("min_area", e.target.value ? Number(e.target.value) : undefined)}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("filter.maxArea")}</label>
          <input
            type="number"
            className="input-field w-full"
            placeholder="Max"
            min={0}
            value={filters.max_area ?? ""}
            onChange={(e) => set("max_area", e.target.value ? Number(e.target.value) : undefined)}
          />
        </div>

        {filters.subcategory && filters.subcategory !== "land" && (
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">{t("filter.bedroomsMin")}</label>
            <input
              type="number"
              className="input-field w-full"
              placeholder="Min"
              min={0}
              value={filters.bedrooms ?? ""}
              onChange={(e) => set("bedrooms", e.target.value ? Number(e.target.value) : undefined)}
            />
          </div>
        )}
      </div>
    </div>
  );
}
