// Evaluation tab: generic rendering of /api/eval/results plus the LLM cost table.
import { FlaskConical, RotateCw } from "lucide-react";
import { api } from "../api";
import { useAsync } from "../hooks";
import { useI18n, type Lang } from "../i18n";
import { formatNumber } from "../format";
import type { CostStats, EvalResults } from "../types";
import { Button, Card, ErrorBox, Spinner } from "./ui";

export function EvalTab() {
  const { t } = useI18n();
  const results = useAsync<EvalResults>(api.evalResults);
  const cost = useAsync<CostStats>(api.costStats);
  const refresh = (reload: () => void, loading: boolean) => (
    <Button size="sm" variant="ghost" onClick={reload} loading={loading} icon={<RotateCw className="h-3.5 w-3.5" aria-hidden />}>
      {t("common.refresh")}
    </Button>
  );

  return (
    <div className="space-y-4">
      <Card title={t("eval.title")} actions={refresh(results.reload, results.loading)}>
        {results.error && <ErrorBox message={results.error} onRetry={results.reload} />}
        {results.loading && !results.data && <Spinner label={t("common.loading")} />}
        {results.data && Object.keys(results.data).length === 0 && (
          <div className="flex items-start gap-3 rounded border border-dashed border-neutral-300 p-4 text-sm text-neutral-700">
            <FlaskConical className="h-5 w-5 shrink-0 text-neutral-500" aria-hidden />
            <p>{t("eval.empty")}</p>
          </div>
        )}
        {results.data && Object.keys(results.data).length > 0 && <JsonBlock value={results.data} depth={0} />}
      </Card>

      <Card title={t("cost.title")} actions={refresh(cost.reload, cost.loading)}>
        {cost.error && <ErrorBox message={cost.error} onRetry={cost.reload} />}
        {cost.loading && !cost.data && <Spinner label={t("common.loading")} />}
        {cost.data && <CostTable stats={cost.data} />}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- generic JSON rendering

type Primitive = string | number | boolean | null;
type Obj = Record<string, unknown>;

const isPrimitive = (v: unknown): v is Primitive => v === null || ["string", "number", "boolean"].includes(typeof v);
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isFlat = (v: unknown): v is Record<string, Primitive> => isObj(v) && Object.values(v).every(isPrimitive);
const humanise = (key: string) => key.replace(/_/g, " ");
const MAX_ROWS = 100;
const MAX_DEPTH = 4;

function formatValue(v: Primitive, lang: Lang): string {
  if (v === null) return "—";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return formatNumber(v, lang);
    return formatNumber(v, lang, Math.abs(v) < 1 ? 3 : 2);
  }
  return String(v);
}

/** Objects of scalars -> key/value table; objects of flat objects -> matrix; arrays of flat objects -> table. */
function JsonBlock({ value, depth }: { value: unknown; depth: number }) {
  const { lang } = useI18n();
  if (isPrimitive(value)) return <span>{formatValue(value, lang)}</span>;
  if (depth > MAX_DEPTH) return <pre className="overflow-x-auto rounded bg-neutral-50 p-2 text-xs">{JSON.stringify(value, null, 2)}</pre>;

  if (Array.isArray(value)) {
    if (value.every(isPrimitive)) return <span>{value.map((v) => formatValue(v, lang)).join(", ")}</span>;
    if (value.every(isFlat)) return <RowsTable rows={value} />;
    return (
      <ol className="space-y-2">
        {value.map((v, i) => (
          <li key={i}>
            <JsonBlock value={v} depth={depth + 1} />
          </li>
        ))}
      </ol>
    );
  }

  const obj = value as Obj;
  const entries = Object.entries(obj);
  const values = entries.map(([, v]) => v);
  if (values.length > 1 && values.every(isFlat)) return <MatrixTable obj={obj as Record<string, Record<string, Primitive>>} />;

  const scalars = entries.filter(([, v]) => isPrimitive(v) || (Array.isArray(v) && v.every(isPrimitive)));
  const nested = entries.filter(([, v]) => !(isPrimitive(v) || (Array.isArray(v) && v.every(isPrimitive))));
  const Heading = depth === 0 ? "h3" : "h4";
  return (
    <div className="space-y-4">
      {scalars.length > 0 && <KeyValueTable entries={scalars} />}
      {nested.map(([k, v]) => (
        <section key={k}>
          <Heading className={`mb-2 font-semibold text-neutral-900 ${depth === 0 ? "text-sm" : "text-xs uppercase tracking-wide text-neutral-600"}`}>
            {humanise(k)}
          </Heading>
          <div className={depth === 0 ? "" : "pl-3"}>
            <JsonBlock value={v} depth={depth + 1} />
          </div>
        </section>
      ))}
    </div>
  );
}

const TH = "border-b border-neutral-200 px-2 py-1.5 text-left text-xs font-semibold text-neutral-600";
const TD = "border-b border-neutral-100 px-2 py-1.5";

function Cell({ v, right }: { v: unknown; right: boolean }) {
  const { lang } = useI18n();
  const text = isPrimitive(v) ? formatValue(v, lang) : JSON.stringify(v);
  return <td className={`${TD} ${right ? "text-right tabular-nums" : ""}`}>{text}</td>;
}

/** Numeric columns are right-aligned, header included. */
const isNumericCol = (rows: Record<string, unknown>[], col: string) => rows.some((r) => typeof r[col] === "number");

function KeyValueTable({ entries }: { entries: [string, unknown][] }) {
  const { t, lang } = useI18n();
  return (
    <div className="overflow-x-auto">
      <table className="min-w-[320px] text-sm">
        <thead>
          <tr>
            <th scope="col" className={TH}>{t("eval.metric")}</th>
            <th scope="col" className={`${TH} text-right`}>{t("eval.value")}</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k}>
              <th scope="row" className={`${TD} text-left font-normal text-neutral-700`}>{humanise(k)}</th>
              {Array.isArray(v) ? <td className={TD}>{(v as Primitive[]).map((x) => formatValue(x, lang)).join(", ")}</td> : <Cell v={v} right />}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function columnsOf(rows: Record<string, unknown>[]): string[] {
  const cols: string[] = [];
  for (const r of rows) for (const k of Object.keys(r)) if (!cols.includes(k)) cols.push(k);
  return cols;
}

function MatrixTable({ obj }: { obj: Record<string, Record<string, Primitive>> }) {
  const rows = Object.entries(obj);
  const cols = columnsOf(rows.map(([, r]) => r));
  const numeric = cols.map((c) => isNumericCol(rows.map(([, r]) => r), c));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            <th scope="col" className={TH} />
            {cols.map((c, i) => (
              <th key={c} scope="col" className={`${TH} ${numeric[i] ? "text-right" : ""}`}>{humanise(c)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, r]) => (
            <tr key={name}>
              <th scope="row" className={`${TD} text-left font-medium`}>{humanise(name)}</th>
              {cols.map((c, i) => (
                <Cell key={c} v={r[c] ?? null} right={numeric[i]} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RowsTable({ rows }: { rows: Record<string, Primitive>[] }) {
  const { t } = useI18n();
  const cols = columnsOf(rows);
  const numeric = cols.map((c) => isNumericCol(rows, c));
  return (
    <div className="max-h-96 overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-white">
          <tr>
            {cols.map((c, i) => (
              <th key={c} scope="col" className={`${TH} ${numeric[i] ? "text-right" : ""}`}>{humanise(c)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, MAX_ROWS).map((r, i) => (
            <tr key={i}>
              {cols.map((c, j) => (
                <Cell key={c} v={r[c] ?? null} right={numeric[j]} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > MAX_ROWS && <p className="mt-1 text-xs text-neutral-500">{t("eval.more", { n: rows.length - MAX_ROWS })}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- cost

function CostTable({ stats }: { stats: CostStats }) {
  const { t, lang } = useI18n();
  const models = Object.entries(stats.by_model);
  const prices = Object.entries(stats.prices_usd_per_m)
    .map(([m, [pin, pout]]) => `${m}: ${formatNumber(pin, lang, 2)} / ${formatNumber(pout, lang, 2)}`)
    .join("; ");
  const sum = (f: (c: (typeof models)[number][1]) => number) => models.reduce((acc, [, c]) => acc + f(c), 0);
  const num = (v: number | null, digits = 0) => (v === null ? "—" : formatNumber(v, lang, digits));

  return (
    <div>
      {models.length === 0 ? (
        <p className="text-sm text-neutral-600">{t("cost.empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr>
                <th scope="col" className={TH}>{t("cost.model")}</th>
                {(["cost.calls", "cost.promptTokens", "cost.completionTokens", "cost.costUsd", "cost.costChf", "cost.p50", "cost.p95"] as const).map((k) => (
                  <th key={k} scope="col" className={`${TH} text-right`}>{t(k)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {models.map(([model, c]) => (
                <tr key={model}>
                  <th scope="row" className={`${TD} text-left font-mono text-xs font-normal`}>{model}</th>
                  <td className={`${TD} text-right`}>{num(c.calls)}</td>
                  <td className={`${TD} text-right`}>{num(c.prompt_tokens)}</td>
                  <td className={`${TD} text-right`}>{num(c.completion_tokens)}</td>
                  <td className={`${TD} text-right`}>{num(c.cost_usd, 4)}</td>
                  <td className={`${TD} text-right`}>{num(c.cost_chf, 4)}</td>
                  <td className={`${TD} text-right`}>{num(c.latency_p50_s, 2)}</td>
                  <td className={`${TD} text-right`}>{num(c.latency_p95_s, 2)}</td>
                </tr>
              ))}
            </tbody>
            {models.length > 1 && (
              <tfoot className="font-semibold tabular-nums">
                <tr>
                  <th scope="row" className="px-2 py-1.5 text-left">{t("cost.total")}</th>
                  <td className="px-2 py-1.5 text-right">{num(sum((c) => c.calls))}</td>
                  <td className="px-2 py-1.5 text-right">{num(sum((c) => c.prompt_tokens))}</td>
                  <td className="px-2 py-1.5 text-right">{num(sum((c) => c.completion_tokens))}</td>
                  <td className="px-2 py-1.5 text-right">{num(sum((c) => c.cost_usd), 4)}</td>
                  <td className="px-2 py-1.5 text-right">{num(sum((c) => c.cost_chf), 4)}</td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
      <p className="mt-3 text-xs text-neutral-500">{t("cost.note", { prices, rate: formatNumber(stats.usd_to_chf, lang, 2) })}</p>
    </div>
  );
}
