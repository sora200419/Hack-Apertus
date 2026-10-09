// Left panel: pick a demo product or upload a BOM as CSV.
import { useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { FileUp, Package, Upload } from "lucide-react";
import { api, errorMessage } from "../api";
import { useI18n } from "../i18n";
import { formatHs } from "../format";
import type { AsyncState } from "../hooks";
import type { Product, ProductSummary } from "../types";
import { Button, Card, ErrorBox, Spinner } from "./ui";

const CSV_HEADER = "line_id,description,hs6,origin_country,value_chf,supplier\n";

interface Props {
  products: AsyncState<ProductSummary[]>;
  currentId: string | null;
  onLoad: (product: Product) => void;
}

export function ProductPanel({ products, currentId, onLoad }: Props) {
  const { t } = useI18n();
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function pick(id: string) {
    setLoadingId(id);
    setError(null);
    try {
      onLoad(await api.product(id));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <div className="space-y-4">
      <Card title={t("panel.demo")}>
        {products.loading && <Spinner label={t("common.loading")} />}
        {products.error && <ErrorBox message={products.error} onRetry={products.reload} />}
        {products.data?.length === 0 && <p className="text-sm text-neutral-600">{t("panel.noProducts")}</p>}
        <ul className="space-y-2" aria-label={t("panel.demoLabel")}>
          {products.data?.map((p) => (
            <li key={p.product_id}>
              <button
                type="button"
                aria-pressed={currentId === p.product_id}
                onClick={() => pick(p.product_id)}
                disabled={loadingId !== null}
                className={`w-full rounded border px-3 py-2 text-left transition-colors ${
                  currentId === p.product_id
                    ? "border-neutral-900 bg-neutral-50"
                    : "border-neutral-200 hover:border-neutral-400"
                }`}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5 text-sm font-medium text-neutral-900">
                    <Package className="h-4 w-4 shrink-0 text-neutral-500" aria-hidden />
                    {p.name}
                  </span>
                  <span className="font-mono text-xs text-neutral-500">{formatHs(p.hs6)}</span>
                </span>
                <span className="mt-0.5 line-clamp-2 block text-xs text-neutral-600">{p.description}</span>
                {loadingId === p.product_id && <Spinner label={t("common.loading")} />}
              </button>
            </li>
          ))}
        </ul>
        {error && (
          <div className="mt-3">
            <ErrorBox message={error} />
          </div>
        )}
      </Card>

      <UploadForm onLoad={onLoad} />
    </div>
  );
}

function UploadForm({ onLoad }: { onLoad: (product: Product) => void }) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [hs6, setHs6] = useState("");
  const [description, setDescription] = useState("");
  const [csv, setCsv] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const priceNum = Number(price);
  const hsDigits = hs6.replace(/\D/g, "");
  const invalid = {
    name: name.trim() === "",
    price: !(priceNum > 0),
    hs6: hs6.trim() !== "" && hsDigits.length !== 6,
    csv: csv.trim() === "",
  };
  const hasErrors = Object.values(invalid).some(Boolean);

  async function readFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsv(await file.text());
    if (!name) setName(file.name.replace(/\.csv$/i, ""));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (hasErrors) return;
    setBusy(true);
    setError(null);
    try {
      onLoad(
        await api.parseBom({
          csv,
          name: name.trim(),
          ex_works_chf: priceNum,
          ...(hsDigits ? { hs6: hsDigits } : {}),
          ...(description.trim() ? { description: description.trim() } : {}),
        }),
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const field = "mt-1 block w-full rounded border border-neutral-300 px-2 py-1.5 text-sm focus:border-neutral-900";
  const bad = "border-red-500";

  return (
    <Card title={t("panel.upload")}>
      <form onSubmit={submit} noValidate className="space-y-3">
        <p className="text-xs text-neutral-600">{t("panel.uploadHint")}</p>
        <Field label={t("form.name")} error={touched && invalid.name ? t("form.required") : null} id="up-name">
          <input id="up-name" className={`${field} ${touched && invalid.name ? bad : ""}`} value={name}
            onChange={(e) => setName(e.target.value)} aria-invalid={touched && invalid.name} />
        </Field>
        <Field label={t("form.exWorks")} error={touched && invalid.price ? t("form.invalidPrice") : null} id="up-price">
          <input id="up-price" type="number" min="0" step="0.01" inputMode="decimal"
            className={`${field} ${touched && invalid.price ? bad : ""}`} value={price}
            onChange={(e) => setPrice(e.target.value)} aria-invalid={touched && invalid.price} />
        </Field>
        <Field label={t("form.hs6")} error={invalid.hs6 ? t("form.invalidHs") : null} id="up-hs6">
          <input id="up-hs6" inputMode="numeric" placeholder="8413.70" className={`${field} font-mono ${invalid.hs6 ? bad : ""}`}
            value={hs6} onChange={(e) => setHs6(e.target.value)} aria-invalid={invalid.hs6} />
        </Field>
        <Field label={t("form.description")} id="up-desc">
          <input id="up-desc" className={field} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label={t("form.csv")} error={touched && invalid.csv ? t("form.required") : null} id="up-csv" hint={t("form.csvHint")}>
          <textarea id="up-csv" rows={6} spellCheck={false}
            className={`${field} font-mono text-xs ${touched && invalid.csv ? bad : ""}`} value={csv}
            onChange={(e) => setCsv(e.target.value)} aria-invalid={touched && invalid.csv} />
        </Field>
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 text-xs font-medium text-neutral-700 ring-1 ring-inset ring-neutral-300 hover:bg-neutral-50 focus-within:outline focus-within:outline-2 focus-within:outline-accent">
            <FileUp className="h-3.5 w-3.5" aria-hidden />
            {t("form.file")}
            <input type="file" accept=".csv,text/csv,text/plain" className="sr-only" onChange={readFile} />
          </label>
          {csv.trim() === "" && (
            <Button size="sm" variant="ghost" onClick={() => setCsv(CSV_HEADER)}>
              {t("form.template")}
            </Button>
          )}
        </div>
        {error && <ErrorBox message={error} />}
        <Button type="submit" variant="primary" loading={busy} icon={<Upload className="h-4 w-4" aria-hidden />} className="w-full">
          {t("form.load")}
        </Button>
      </form>
    </Card>
  );
}

function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-neutral-800">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-[11px] text-neutral-500">{hint}</p>}
      {error && (
        <p className="mt-1 text-xs text-red-700" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
