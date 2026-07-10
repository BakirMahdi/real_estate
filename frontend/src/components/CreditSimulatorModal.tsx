import { useEffect, useState } from "react";
import { Calculator, Loader2, TriangleAlert, X } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Property } from "../types/property";
import { calculatePurchasingCapacity, simulateCredit } from "../lib/creditSimulator";
import { formatArea, formatPrice, governorateOf, sourceLabel } from "../lib/format";

function formatTND(value: number): string {
  return formatPrice(Math.round(value));
}

const ANNUAL_RATE = 7.5;

export function CreditSimulatorModal({
  property,
  onClose,
}: {
  property: Property;
  onClose: () => void;
}) {
  const defaultPrice = property.price ?? 0;
  const [propertyPrice, setPropertyPrice] = useState(defaultPrice);
  const [downPayment, setDownPayment] = useState<number | "">("");
  const [years, setYears] = useState<number | "">("");
  const [monthlyIncome, setMonthlyIncome] = useState<number | "">("");

  const [alternatives, setAlternatives] = useState<Property[] | null>(null);
  const [loadingAlternatives, setLoadingAlternatives] = useState(false);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const hasMonthlyIncome = monthlyIncome !== "" && monthlyIncome > 0;
  const hasDownPayment = downPayment !== "";
  const hasYears = years !== "" && years > 0;
  const canSimulate = hasMonthlyIncome && hasDownPayment && hasYears;

  const result = canSimulate
    ? simulateCredit({
        propertyPrice,
        downPayment,
        annualRatePercent: ANNUAL_RATE,
        years,
        monthlyIncome,
      })
    : null;

  const ratioColor =
    result?.debtToIncomeRatio == null
      ? ""
      : result.debtToIncomeRatio <= 0.35
        ? "text-emerald-600"
        : result.debtToIncomeRatio <= 0.5
          ? "text-amber-600"
          : "text-red-600";

  const capacity = canSimulate
    ? calculatePurchasingCapacity({
        monthlyIncome,
        downPayment,
        annualRatePercent: ANNUAL_RATE,
        years,
      })
    : null;

  const exceedsCapacity = capacity != null && capacity.maxAffordablePrice < propertyPrice;

  useEffect(() => {
    if (!exceedsCapacity || capacity == null) {
      setAlternatives(null);
      return;
    }

    let cancelled = false;
    setLoadingAlternatives(true);
    const timeout = setTimeout(() => {
      api
        .searchProperties({
          listing_type: "sale",
          subcategory: property.subcategory ?? undefined,
          city: property.governorate ?? undefined,
          max_price: Math.max(Math.round(capacity.maxAffordablePrice), 0),
          limit: 10,
        })
        .then((res) => {
          if (cancelled) return;
          // Exclude the current listing, ones with an undisclosed price
          // (stored as 0, which numerically satisfies any max_price filter
          // but isn't actually verified to fit the budget), and obvious
          // placeholder prices (e.g. "1 DT") that aren't real asking prices.
          setAlternatives(
            res.items
              .filter((p) => p.id !== property.id && p.price != null && p.price > 1000)
              .slice(0, 4),
          );
        })
        .catch(() => {
          if (!cancelled) setAlternatives([]);
        })
        .finally(() => {
          if (!cancelled) setLoadingAlternatives(false);
        });
    }, 400);

    return () => {
      cancelled = true;
      clearTimeout(timeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exceedsCapacity, capacity?.maxAffordablePrice, property.id]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass max-h-[90vh] w-full max-w-lg overflow-y-auto p-6 shadow-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-6 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-600/20">
              <Calculator className="h-5 w-5 text-brand-400" />
            </div>
            <div>
              <h2 className="font-display text-lg font-semibold text-slate-900">
                Simulateur de crédit
              </h2>
              <p className="text-xs text-slate-400">{property.title}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">
              Prix du bien (TND)
            </span>
            <input
              type="number"
              min={0}
              className="input-field"
              value={propertyPrice}
              onChange={(e) => setPropertyPrice(Number(e.target.value) || 0)}
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">
              Apport personnel (TND) <span className="text-red-500">*</span>
            </span>
            <input
              type="number"
              min={0}
              required
              className="input-field"
              placeholder="Requis pour la simulation"
              value={downPayment}
              onChange={(e) =>
                setDownPayment(e.target.value === "" ? "" : Number(e.target.value) || 0)
              }
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">
              Durée du prêt (années) <span className="text-red-500">*</span>
            </span>
            <input
              type="number"
              min={1}
              max={30}
              required
              className="input-field"
              placeholder="Requis pour la simulation"
              value={years}
              onChange={(e) =>
                setYears(e.target.value === "" ? "" : Number(e.target.value) || 0)
              }
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">
              Revenu mensuel net (TND) <span className="text-red-500">*</span>
            </span>
            <input
              type="number"
              min={0}
              required
              className="input-field"
              placeholder="Requis pour la simulation"
              value={monthlyIncome}
              onChange={(e) =>
                setMonthlyIncome(e.target.value === "" ? "" : Number(e.target.value) || 0)
              }
            />
          </label>
        </div>

        {!canSimulate && (
          <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-700">
            Veuillez renseigner l'apport personnel, la durée du prêt et votre revenu mensuel net
            pour lancer la simulation.
          </p>
        )}

        {result != null && (
          <div className="mt-6 rounded-xl border border-slate-100 bg-white p-5">
            <p className="text-xs text-slate-400">Mensualité estimée</p>
            <p className="font-display text-3xl font-extrabold text-brand-400">
              {formatTND(result.monthlyPayment)}
              <span className="ml-1 text-base font-medium text-slate-400">/ mois</span>
            </p>

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <div>
                <p className="text-xs text-slate-400">Montant emprunté</p>
                <p className="font-medium text-slate-900">{formatTND(result.loanAmount)}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400">Coût total du crédit</p>
                <p className="font-medium text-slate-900">{formatTND(result.totalInterest)}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400">Total remboursé</p>
                <p className="font-medium text-slate-900">{formatTND(result.totalPaid)}</p>
              </div>
            </div>

            {result.debtToIncomeRatio != null && (
              <p className={`mt-4 text-sm font-medium ${ratioColor}`}>
                Taux d'endettement : {(result.debtToIncomeRatio * 100).toFixed(1)}%
                {result.debtToIncomeRatio > 0.5
                  ? " — largement au-dessus du seuil recommandé (35%)"
                  : result.debtToIncomeRatio > 0.35
                    ? " — au-dessus du seuil recommandé (35%)"
                    : " — dans la limite recommandée"}
              </p>
            )}
          </div>
        )}

        {capacity != null && (
          <div className="mt-4 rounded-xl border border-slate-100 bg-white p-5">
            <p className="text-xs text-slate-400">Capacité d'achat estimée</p>
            <p className="font-display text-2xl font-bold text-slate-900">
              {formatTND(capacity.maxAffordablePrice)}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Basée sur une mensualité maximale recommandée de {formatTND(capacity.maxMonthlyPayment)}
              {" "}(35% de votre revenu), apport personnel inclus.
            </p>

            {exceedsCapacity && (
              <div className="mt-4 border-t border-slate-100 pt-4">
                <p className="flex items-center gap-2 text-sm font-medium text-amber-600">
                  <TriangleAlert className="h-4 w-4 shrink-0" />
                  Ce bien dépasse votre capacité d'achat de{" "}
                  {formatTND(propertyPrice - capacity.maxAffordablePrice)}.
                </p>

                {loadingAlternatives && (
                  <p className="mt-3 flex items-center gap-2 text-sm text-slate-400">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Recherche de biens plus adaptés à votre budget…
                  </p>
                )}

                {!loadingAlternatives && alternatives != null && alternatives.length > 0 && (
                  <div className="mt-3 space-y-2">
                    <p className="text-xs font-medium text-slate-500">
                      Alternatives dans votre budget
                    </p>
                    {alternatives.map((alt) => (
                      <Link
                        key={alt.id}
                        to={`/property/${alt.id}`}
                        className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 p-3 text-sm transition hover:border-brand-300 hover:bg-brand-50"
                      >
                        <div className="min-w-0">
                          <p className="truncate font-medium text-slate-900">{alt.title}</p>
                          <p className="text-xs text-slate-400">
                            {governorateOf(alt)} · {formatArea(alt.area)} · {sourceLabel(alt.source)}
                          </p>
                        </div>
                        <p className="shrink-0 font-semibold text-brand-400">
                          {formatPrice(alt.price)}
                        </p>
                      </Link>
                    ))}
                  </div>
                )}

                {!loadingAlternatives && alternatives != null && alternatives.length === 0 && (
                  <p className="mt-3 text-sm text-slate-400">
                    Aucun bien similaire trouvé dans votre budget pour le moment.
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        <p className="mt-4 text-xs text-slate-400">
          Estimation indicative, hors assurance et frais de dossier. Ne constitue pas une offre de
          prêt.
        </p>
      </div>
    </div>
  );
}
