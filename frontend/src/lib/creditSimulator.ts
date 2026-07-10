// Pure loan-amortization math for the credit simulator. No React/UI concerns
// here so the calculation can be unit-tested and reused independently of the
// modal that collects the inputs.

export interface CreditSimulationInput {
  propertyPrice: number;
  downPayment: number;
  annualRatePercent: number;
  years: number;
  monthlyIncome?: number;
}

export interface CreditSimulationResult {
  loanAmount: number;
  numberOfPayments: number;
  monthlyPayment: number;
  totalPaid: number;
  totalInterest: number;
  /** Share of monthly income the payment would consume, or null if no income was given. */
  debtToIncomeRatio: number | null;
}

/**
 * Standard fixed-rate amortization formula:
 * M = P * r(1+r)^n / ((1+r)^n - 1), falling back to a straight split when the
 * rate is 0 (which would otherwise divide by zero).
 */
export function simulateCredit(input: CreditSimulationInput): CreditSimulationResult {
  const loanAmount = Math.max(input.propertyPrice - input.downPayment, 0);
  const numberOfPayments = Math.max(Math.round(input.years * 12), 1);
  const monthlyRate = input.annualRatePercent / 100 / 12;

  let monthlyPayment: number;
  if (loanAmount === 0) {
    monthlyPayment = 0;
  } else if (monthlyRate === 0) {
    monthlyPayment = loanAmount / numberOfPayments;
  } else {
    const growth = Math.pow(1 + monthlyRate, numberOfPayments);
    monthlyPayment = (loanAmount * monthlyRate * growth) / (growth - 1);
  }

  const totalPaid = monthlyPayment * numberOfPayments;
  const totalInterest = totalPaid - loanAmount;
  const debtToIncomeRatio =
    input.monthlyIncome && input.monthlyIncome > 0 ? monthlyPayment / input.monthlyIncome : null;

  return {
    loanAmount,
    numberOfPayments,
    monthlyPayment,
    totalPaid,
    totalInterest,
    debtToIncomeRatio,
  };
}

export interface PurchasingCapacityInput {
  monthlyIncome: number;
  downPayment: number;
  annualRatePercent: number;
  years: number;
  /** Max share of monthly income a bank will lend against; defaults to the same 35% threshold used to flag debt ratio as risky. */
  maxDebtRatio?: number;
}

export interface PurchasingCapacityResult {
  maxMonthlyPayment: number;
  maxLoanAmount: number;
  /** The most a buyer could pay for a property: max loan + down payment. */
  maxAffordablePrice: number;
}

/**
 * Algebraic inverse of simulateCredit's amortization formula: given a max
 * monthly payment (income x max debt ratio), solve for the loan amount it
 * supports, P = M * ((1+r)^n - 1) / (r(1+r)^n), then add the down payment
 * back to get the max affordable property price ("capacité d'achat").
 */
export function calculatePurchasingCapacity(
  input: PurchasingCapacityInput,
): PurchasingCapacityResult {
  const maxDebtRatio = input.maxDebtRatio ?? 0.35;
  const maxMonthlyPayment = Math.max(input.monthlyIncome, 0) * maxDebtRatio;
  const numberOfPayments = Math.max(Math.round(input.years * 12), 1);
  const monthlyRate = input.annualRatePercent / 100 / 12;

  let maxLoanAmount: number;
  if (monthlyRate === 0) {
    maxLoanAmount = maxMonthlyPayment * numberOfPayments;
  } else {
    const growth = Math.pow(1 + monthlyRate, numberOfPayments);
    maxLoanAmount = (maxMonthlyPayment * (growth - 1)) / (monthlyRate * growth);
  }

  return {
    maxMonthlyPayment,
    maxLoanAmount,
    maxAffordablePrice: maxLoanAmount + Math.max(input.downPayment, 0),
  };
}
