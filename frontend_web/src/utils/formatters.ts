const PT_BR = "pt-BR";

type NumericInput = string | number | null | undefined;

const currencyFormatter = new Intl.NumberFormat(PT_BR, {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const decimal2Formatter = new Intl.NumberFormat(PT_BR, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const quantityFormatter = new Intl.NumberFormat(PT_BR, {
  minimumFractionDigits: 0,
  maximumFractionDigits: 8,
});

export function formatCurrencyBR(value: NumericInput, fallback = "Nao informado") {
  const amount = parseBrazilianNumber(value);
  return amount === null ? fallback : currencyFormatter.format(amount).replace(/\u00a0/g, " ");
}

export function formatPercentBR(value: NumericInput, fallback = "Nao informado") {
  const amount = parseBrazilianNumber(value);
  return amount === null ? fallback : `${decimal2Formatter.format(amount)}%`;
}

export function formatQuantityBR(value: NumericInput, fallback = "Nao informado") {
  const amount = parseBrazilianNumber(value);
  return amount === null ? fallback : quantityFormatter.format(amount);
}

export function formatDecimalBR(value: NumericInput, fractionDigits = 2, fallback = "Nao informado") {
  const amount = parseBrazilianNumber(value);
  if (amount === null) return fallback;
  return new Intl.NumberFormat(PT_BR, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(amount);
}

export function parseBrazilianNumber(value: NumericInput): number | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;

  const input = value.trim().replace(/\s/g, "");
  if (!input) return null;

  const withoutCurrency = input.replace(/^R\$?/, "");
  const cleaned = withoutCurrency.replace(/[^\d,.-]/g, "");
  if (!cleaned || cleaned === "-" || cleaned === "," || cleaned === ".") return null;

  const sign = cleaned.startsWith("-") ? "-" : "";
  const unsigned = cleaned.replace(/-/g, "");
  const lastComma = unsigned.lastIndexOf(",");
  const lastDot = unsigned.lastIndexOf(".");
  const hasComma = lastComma >= 0;
  const hasDot = lastDot >= 0;
  const decimalIndex = decimalSeparatorIndex(unsigned, hasComma, hasDot, lastComma, lastDot);

  let normalized: string;
  if (decimalIndex >= 0) {
    const integerPart = unsigned.slice(0, decimalIndex).replace(/[.,]/g, "");
    const decimalPart = unsigned.slice(decimalIndex + 1).replace(/[.,]/g, "");
    normalized = `${sign}${integerPart || "0"}.${decimalPart}`;
  } else {
    normalized = `${sign}${unsigned.replace(/[.,]/g, "")}`;
  }

  const amount = Number(normalized);
  return Number.isFinite(amount) ? amount : null;
}

function decimalSeparatorIndex(value: string, hasComma: boolean, hasDot: boolean, lastComma: number, lastDot: number) {
  if (hasComma && hasDot) return Math.max(lastComma, lastDot);
  if (hasComma) return lastComma;
  if (!hasDot) return -1;

  const parts = value.split(".");
  if (parts.length > 2) return -1;

  const decimalPart = parts[1] ?? "";
  const integerPart = parts[0] ?? "";
  if (decimalPart.length === 3 && (integerPart.length === 1 || integerPart.length === 3)) return -1;
  return lastDot;
}
export function normalizeDecimalForApi(value: NumericInput, fallback = "0") {
  const amount = parseBrazilianNumber(value);
  if (amount === null) return fallback;
  return amount.toFixed(8).replace(/\.?(0+)$/, (match) => (match.startsWith(".") ? "" : ""));
}

export function sanitizeBrazilianDecimalInput(value: string) {
  const sanitized = value.replace(/[^\d,.-]/g, "");
  const negative = sanitized.startsWith("-");
  return `${negative ? "-" : ""}${sanitized.replace(/-/g, "")}`;
}

export function formatCurrencyInputBR(value: NumericInput) {
  const amount = parseBrazilianNumber(value);
  return amount === null ? "" : decimal2Formatter.format(amount);
}

export function toNumber(value: NumericInput): number | null {
  return parseBrazilianNumber(value);
}

export function formatMoney(value: NumericInput, currency = "R$") {
  if (currency === "R$" || currency === "BRL") {
    return formatCurrencyBR(value, "Nao informado");
  }
  const amount = parseBrazilianNumber(value);
  return amount === null ? "Nao informado" : `${currency} ${decimal2Formatter.format(amount)}`;
}

export function formatPercent(value: NumericInput) {
  return formatPercentBR(value, "Nao informado");
}

export function display(value: NumericInput) {
  if (value === null || value === undefined || value === "") return "Nao informado";
  return String(value);
}
