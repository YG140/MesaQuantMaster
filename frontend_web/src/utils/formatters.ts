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
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "number") {
    return Number.isFinite(value) ? trimDecimalString(String(value)) : fallback;
  }
  return decimalTextToApi(value) ?? fallback;
}

export function sanitizeBrazilianDecimalInput(value: string) {
  const sanitized = value.replace(/[^\d,.-]/g, "");
  const negative = sanitized.startsWith("-");
  return `${negative ? "-" : ""}${sanitized.replace(/-/g, "")}`;
}

export function formatCurrencyInputBR(value: NumericInput) {
  return decimalToCurrencyDisplay(value);
}

export function digitsToCurrencyDisplay(digits: string, negative = false) {
  const onlyDigits = digits.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
  if (!onlyDigits) return "0,00";
  const cents = onlyDigits.padStart(3, "0");
  const integerPart = cents.slice(0, -2).replace(/^0+(?=\d)/, "") || "0";
  const decimalPart = cents.slice(-2);
  const groupedInteger = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${negative ? "-" : ""}${groupedInteger},${decimalPart}`;
}

export function decimalToCurrencyDisplay(value: NumericInput) {
  const decimal = decimalTextToApi(value);
  if (decimal === null) return "0,00";
  const negative = decimal.startsWith("-");
  const unsigned = negative ? decimal.slice(1) : decimal;
  const [integerPart = "0", fractionPart = ""] = unsigned.split(".");
  const cents = `${integerPart.replace(/^0+(?=\d)/, "") || "0"}${fractionPart.padEnd(2, "0").slice(0, 2)}`;
  return digitsToCurrencyDisplay(cents, negative);
}

export function currencyDisplayToDecimal(value: string, options: { allowNegative?: boolean } = {}) {
  return decimalTextToApi(value, options) ?? "0.00";
}

function decimalTextToApi(value: NumericInput, options: { allowNegative?: boolean } = {}): string | null {
  if (value === null || value === undefined || value === "") return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const negative = options.allowNegative && raw.includes("-");
  const cleaned = raw.replace(/\s/g, "").replace(/^R\$?/, "").replace(/[^\d,.-]/g, "");
  const unsigned = cleaned.replace(/-/g, "");
  if (!/\d/.test(unsigned)) return null;

  const lastComma = unsigned.lastIndexOf(",");
  const lastDot = unsigned.lastIndexOf(".");
  const decimalIndex = decimalSeparatorIndex(unsigned, lastComma >= 0, lastDot >= 0, lastComma, lastDot);
  let integerPart: string;
  let fractionPart: string;

  if (decimalIndex >= 0) {
    integerPart = unsigned.slice(0, decimalIndex).replace(/[.,]/g, "") || "0";
    fractionPart = unsigned.slice(decimalIndex + 1).replace(/[.,]/g, "");
  } else {
    integerPart = unsigned.replace(/[.,]/g, "") || "0";
    fractionPart = "";
  }

  const normalizedInteger = integerPart.replace(/^0+(?=\d)/, "") || "0";
  const normalizedFraction = fractionPart.replace(/0+$/, "");
  const decimal = normalizedFraction ? `${normalizedInteger}.${normalizedFraction}` : normalizedInteger;
  return `${negative ? "-" : ""}${trimDecimalString(decimal)}`;
}

function trimDecimalString(value: string) {
  if (!value.includes(".")) return value;
  return value.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
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

export function formatDateTimeBR(value: string | null | undefined) {
  if (!value) return "Nao informado";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Nao informado";
  return new Intl.DateTimeFormat(PT_BR, {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export function display(value: NumericInput) {
  if (value === null || value === undefined || value === "") return "Nao informado";
  return String(value);
}
