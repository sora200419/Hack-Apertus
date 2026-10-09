// Typed client for the OriginPass FastAPI backend (same origin; /api is proxied by Vite or nginx).
import type {
  BomParseRequest,
  ClassifyBomResponse,
  CostStats,
  Dossier,
  EvalResults,
  EvaluateResponse,
  HSSuggestion,
  Health,
  Product,
  ProductSummary,
  RulePack,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI errors: {detail: string} or {detail: [{loc, msg}, ...]} for validation errors. */
function detailMessage(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const item = d as { loc?: unknown[]; msg?: string };
        const loc = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
        return loc ? `${loc}: ${item.msg ?? ""}` : (item.msg ?? "");
      })
      .join("; ");
  }
  return null;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}) },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("Cannot reach the API server.", 0);
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!res.ok) {
    throw new ApiError(detailMessage(body) ?? `HTTP ${res.status} ${res.statusText}`, res.status);
  }
  return body as T;
}

const post = <T>(path: string, payload: unknown, signal?: AbortSignal) =>
  request<T>(path, { method: "POST", body: JSON.stringify(payload), signal });

export const api = {
  health: (signal?: AbortSignal) => request<Health>("/health", { signal }),
  products: (signal?: AbortSignal) => request<ProductSummary[]>("/products", { signal }),
  product: (id: string, signal?: AbortSignal) =>
    request<Product>(`/products/${encodeURIComponent(id)}`, { signal }),
  evaluate: (product: Product, signal?: AbortSignal) => post<EvaluateResponse>("/evaluate", product, signal),
  suggestHs: (description: string, k?: number, signal?: AbortSignal) =>
    post<HSSuggestion>("/hs/suggest", k === undefined ? { description } : { description, k }, signal),
  classifyBom: (product: Product, signal?: AbortSignal) =>
    post<ClassifyBomResponse>("/hs/classify-bom", product, signal),
  dossier: (product: Product, signal?: AbortSignal) => post<Dossier>("/dossier", product, signal),
  parseBom: (req: BomParseRequest, signal?: AbortSignal) => post<Product>("/bom/parse", req, signal),
  rulepack: (signal?: AbortSignal) => request<RulePack>("/rulepack", { signal }),
  evalResults: (signal?: AbortSignal) => request<EvalResults>("/eval/results", { signal }),
  costStats: (signal?: AbortSignal) => request<CostStats>("/stats/cost", { signal }),
};

export function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}
