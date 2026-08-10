import { useState } from "react";
import { ChevronDown, Search, SlidersHorizontal, X } from "lucide-react";
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
  const [open, setOpen] = useState(false);
  const set = <K extends keyof SearchFilters>(key: K, value: SearchFilters[K] | "") => {
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
    <div className="glass animate-fade-in p-5">
      {/* Top Section: Search Input and Actions - always visible */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-700 dark:text-gray-600" />
          <input
            type="text"
            className="input-field pl-10 pr-4 py-2.5 w-full bg-white dark:bg-navy-800 border-gray-200 dark:border-white/10 text-navy-700 dark:text-white placeholder-gray-600 rounded-xl focus:border-brand-500/50 focus:ring-1 focus:ring-brand-500/30"
            placeholder={t("filter.search")}
            value={filters.query ?? ""}
            onChange={(e) => set("query", e.target.value)}
          />
        </div>
        <div className="flex items-center justify-between gap-4 shrink-0">
          <button
            type="button"
            onClick={() => setOpen((prev) => !prev)}
            aria-expanded={open}
            className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition ${
              open ? "bg-brand-50 text-brand-600 dark:bg-navy-700 dark:text-brand-200" : "text-navy-700 dark:text-gray-300 hover:bg-lightPrimary dark:hover:bg-navy-700"
            }`}
          >
            <SlidersHorizontal className="h-4 w-4 text-brand-500 dark:text-brand-400" />
            {t("filter.filters")}
            <ChevronDown className={`h-3.5 w-3.5 text-gray-700 dark:text-gray-600 transition-transform duration-300 ${open ? "rotate-180" : ""}`} />
          </button>
          {hasFilters && (
            <button
              type="button"
              onClick={onReset}
              className="flex items-center gap-1 text-xs text-gray-700 dark:text-gray-600 transition hover:text-gray-700 dark:hover:text-gray-600 hover:bg-lightPrimary dark:hover:bg-navy-700 px-2.5 py-1.5 rounded-lg"
            >
              <X className="h-3.5 w-3.5" />
              {t("filter.reset")}
            </button>
          )}
        </div>
      </div>

      {/* Filters dropdown - hidden until "Filtres" is clicked, then grows
          open under the search bar (grid-template-rows 0fr -> 1fr is a
          pure-CSS way to animate to/from "auto" height without measuring). */}
      <div
        className={`grid transition-[grid-template-rows] duration-300 ease-out ${
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
        }`}
      >
        <div className="overflow-hidden">
          <div
            className={`grid gap-4 border-t border-gray-200 dark:border-white/10 pt-4 mt-4 transition-opacity duration-300 sm:grid-cols-2 lg:grid-cols-4 ${
              open ? "opacity-100 delay-100" : "opacity-0"
            }`}
          >
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-600">{t("filter.governorate")}</label>
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
              <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-600">{t("filter.category")}</label>
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
              <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-600">{t("filter.transaction")}</label>
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
              <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-600">{t("filter.minPrice")}</label>
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
              <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-600">{t("filter.maxPrice")}</label>
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
              <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-600">{t("filter.minArea")}</label>
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
              <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-600">{t("filter.maxArea")}</label>
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
                <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-600">{t("filter.bedroomsMin")}</label>
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
      </div>
    </div>
  );
}
