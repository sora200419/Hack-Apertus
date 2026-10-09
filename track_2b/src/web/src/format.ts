// Number and code formatting shared by all views.
import { NUMBER_LOCALE, type Lang } from "./i18n";

export function formatChf(value: number, lang: Lang): string {
  return `CHF ${value.toLocaleString(NUMBER_LOCALE[lang], { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatNumber(value: number, lang: Lang, digits = 0): string {
  return value.toLocaleString(NUMBER_LOCALE[lang], { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatPct(value: number, lang: Lang, digits = 1): string {
  return `${formatNumber(value, lang, digits)}%`;
}

/** Signed percentage points, e.g. +7.7 / −3.2. */
export function formatPp(value: number, lang: Lang): string {
  const abs = formatNumber(Math.abs(value), lang, 1);
  return value >= 0 ? `+${abs}` : `−${abs}`;
}

/** '841370' -> '8413.70'. */
export function formatHs(hs6: string | null | undefined): string {
  if (!hs6) return "—";
  return hs6.length === 6 ? `${hs6.slice(0, 4)}.${hs6.slice(4)}` : hs6;
}
