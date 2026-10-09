// Pure helpers for editing a Product in the what-if simulator.
import type { BomLine, Product } from "./types";

/** Origin choices offered in the BOM table; anything else is typed as an ISO code. */
export const KNOWN_ORIGINS = ["CH", "CN", "DE", "IT", "FR", "AT", "JP", "US", "KR", "TW", "VN"] as const;

export const HS6_RE = /^\d{6}$/;
export const ISO2_RE = /^[A-Z]{2}$/;

export type LinePatch = Partial<Pick<BomLine, "hs6" | "origin_country" | "value_chf">>;

export function patchLine(product: Product, lineId: string, patch: LinePatch): Product {
  return { ...product, bom: product.bom.map((l) => (l.line_id === lineId ? { ...l, ...patch } : l)) };
}

export interface Change {
  lineId: string | null; // null = product-level field
  field: "hs6" | "origin_country" | "value_chf" | "ex_works_chf";
}

/** Field-level differences between the loaded product and the edited one. */
export function diffProduct(original: Product, current: Product): Change[] {
  const changes: Change[] = [];
  if (original.hs6 !== current.hs6) changes.push({ lineId: null, field: "hs6" });
  if (original.ex_works_chf !== current.ex_works_chf) changes.push({ lineId: null, field: "ex_works_chf" });
  const before = new Map(original.bom.map((l) => [l.line_id, l]));
  for (const line of current.bom) {
    const old = before.get(line.line_id);
    if (!old) continue;
    for (const field of ["hs6", "origin_country", "value_chf"] as const) {
      if (old[field] !== line[field]) changes.push({ lineId: line.line_id, field });
    }
  }
  return changes;
}

export function isChanged(changes: Change[], lineId: string | null, field: Change["field"]): boolean {
  return changes.some((c) => c.lineId === lineId && c.field === field);
}
