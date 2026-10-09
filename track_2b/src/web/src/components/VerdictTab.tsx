// Verdict tab: what-if bar, verdict, fixes, duty, editable BOM with HS suggestions, criteria trace.
import { useEffect, useRef, useState } from "react";
import { ArrowRight, CheckCheck, RotateCcw, Sparkles, Wand2 } from "lucide-react";
import { api, errorMessage, isAbort } from "../api";
import { useI18n } from "../i18n";
import { formatPct } from "../format";
import type { Evaluation } from "../hooks";
import { diffProduct, isChanged, patchLine, type LinePatch } from "../product";
import type { Product, Verdict } from "../types";
import { BomTable } from "./BomTable";
import { DutyCard } from "./DutyCard";
import { HsSuggestPanel, isConfident, type SuggestionState } from "./HsSuggestPanel";
import { HsInput, MoneyInput } from "./inputs";
import { Badge, Button, Card, ErrorBox, STATUS_TONE, Spinner, StatusIcon } from "./ui";
import { CriteriaTrace, Fixes, Reasons, VerdictSummary } from "./VerdictCard";

/** Suggestion key for the finished product's own HS code. */
const PRODUCT_KEY = "__product__";

interface Props {
  product: Product;
  original: Product;
  onChange: (update: (p: Product) => Product) => void;
  onReset: () => void;
  evaluation: Evaluation;
  baseline: Verdict | null;
}

export function VerdictTab({ product, original, onChange, onReset, evaluation, baseline }: Props) {
  const { t } = useI18n();
  const [suggestions, setSuggestions] = useState<Record<string, SuggestionState>>({});
  const [classifying, setClassifying] = useState(false);
  const inflight = useRef(new Map<string, AbortController>());
  useEffect(() => () => inflight.current.forEach((c) => c.abort()), []);

  const changes = diffProduct(original, product);
  const result = evaluation.result;
  const missing = product.bom.filter((l) => !l.hs6);
  const confident = product.bom.filter((l) => {
    const s = suggestions[l.line_id];
    return isConfident(s) && s.data.chosen !== l.hs6;
  });

  const setSuggestion = (key: string, state: SuggestionState | null) =>
    setSuggestions((prev) => {
      const next = { ...prev };
      if (state) next[key] = state;
      else delete next[key];
      return next;
    });

  function suggest(key: string, description: string) {
    inflight.current.get(key)?.abort();
    const ctrl = new AbortController();
    inflight.current.set(key, ctrl);
    setSuggestion(key, { loading: true, error: null, data: null });
    api
      .suggestHs(description, undefined, ctrl.signal)
      .then((data) => setSuggestion(key, { loading: false, error: null, data }))
      .catch((err) => {
        if (!isAbort(err)) setSuggestion(key, { loading: false, error: errorMessage(err), data: null });
      });
  }

  function closeSuggestion(key: string) {
    inflight.current.get(key)?.abort();
    setSuggestion(key, null);
  }

  async function classifyMissing() {
    setClassifying(true);
    const ids = missing.map((l) => l.line_id);
    setSuggestions((prev) => ({
      ...prev,
      ...Object.fromEntries(ids.map((id) => [id, { loading: true, error: null, data: null }])),
    }));
    try {
      const res = await api.classifyBom(product);
      setSuggestions((prev) => ({
        ...prev,
        ...Object.fromEntries(Object.entries(res.suggestions).map(([id, data]) => [id, { loading: false, error: null, data }])),
      }));
    } catch (err) {
      const error = errorMessage(err);
      setSuggestions((prev) => ({
        ...prev,
        ...Object.fromEntries(ids.map((id) => [id, { loading: false, error, data: null }])),
      }));
    } finally {
      setClassifying(false);
    }
  }

  function acceptAllConfident() {
    onChange((p) =>
      confident.reduce((acc, l) => {
        const chosen = suggestions[l.line_id]?.data?.chosen;
        return chosen ? patchLine(acc, l.line_id, { hs6: chosen }) : acc;
      }, p),
    );
  }

  const patch = (lineId: string, lp: LinePatch) => onChange((p) => patchLine(p, lineId, lp));
  const productSugg = suggestions[PRODUCT_KEY];

  return (
    <div className="space-y-4">
      {/* What-if bar */}
      <section className="rounded-lg border border-neutral-200 bg-white px-4 py-3" aria-label={t("verdict.whatIf")}>
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <div className="min-w-0 flex-1 basis-56">
            <h2 className="truncate text-base font-semibold text-neutral-900">{product.name}</h2>
            <p className="line-clamp-1 text-xs text-neutral-600">{product.description}</p>
          </div>
          <div>
            <div className="mb-1 text-xs font-medium text-neutral-700">{t("verdict.productHs")}</div>
            <div className="flex items-center gap-1">
              <HsInput
                value={product.hs6}
                changed={isChanged(changes, null, "hs6")}
                label={t("verdict.productHs")}
                onCommit={(hs6) => onChange((p) => ({ ...p, hs6 }))}
              />
              <Button
                size="sm"
                variant="ghost"
                loading={productSugg?.loading}
                onClick={() => suggest(PRODUCT_KEY, `${product.name}. ${product.description}`)}
                aria-label={t("bom.suggestFor", { what: product.name })}
                icon={<Sparkles className="h-3.5 w-3.5" aria-hidden />}
              >
                {t("bom.suggest")}
              </Button>
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs font-medium text-neutral-700">{t("form.exWorks")}</div>
            <MoneyInput
              value={product.ex_works_chf}
              allowZero={false}
              changed={isChanged(changes, null, "ex_works_chf")}
              label={t("form.exWorks")}
              onCommit={(ex_works_chf) => onChange((p) => ({ ...p, ex_works_chf }))}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {changes.length === 0 ? (
              <Badge tone="neutral">{t("diff.original")}</Badge>
            ) : (
              <Badge tone="amber">{changes.length === 1 ? t("diff.one") : t("diff.changes", { n: changes.length })}</Badge>
            )}
            {changes.length > 0 && baseline && <BaselineChip baseline={baseline} current={result?.verdict ?? null} />}
            <Button size="sm" onClick={onReset} disabled={changes.length === 0} icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}>
              {t("diff.reset")}
            </Button>
          </div>
        </div>
        <p className="mt-2 flex items-center gap-2 text-xs text-neutral-600">
          <Wand2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
          {t("verdict.whatIf")}
          {evaluation.loading && <Spinner label={t("verdict.evaluating")} />}
        </p>
        {productSugg && (
          <div className="mt-3">
            <HsSuggestPanel
              subject={product.name}
              state={productSugg}
              current={product.hs6}
              onAccept={(hs6) => onChange((p) => ({ ...p, hs6 }))}
              onRetry={() => suggest(PRODUCT_KEY, `${product.name}. ${product.description}`)}
              onClose={() => closeSuggestion(PRODUCT_KEY)}
            />
          </div>
        )}
      </section>

      {evaluation.error && <ErrorBox message={evaluation.error} onRetry={() => onChange((p) => ({ ...p }))} />}

      {result ? (
        <>
          <VerdictSummary verdict={result.verdict} />
          <div className="grid gap-4 lg:grid-cols-2">
            <Fixes fixes={result.verdict.fixes} />
            <DutyCard duty={result.duty} hs6={result.verdict.hs6} />
          </div>
        </>
      ) : (
        evaluation.loading && (
          <div className="rounded-lg border border-neutral-200 bg-white p-6">
            <Spinner label={t("verdict.evaluating")} />
          </div>
        )
      )}

      <Card
        title={t("bom.title")}
        actions={
          <>
            {confident.length > 0 && (
              <Button size="sm" onClick={acceptAllConfident} icon={<CheckCheck className="h-3.5 w-3.5" aria-hidden />}>
                {t("bom.acceptAll")} ({confident.length})
              </Button>
            )}
            <Button
              size="sm"
              variant="primary"
              loading={classifying}
              disabled={missing.length === 0}
              title={missing.length === 0 ? t("bom.noneMissing") : undefined}
              onClick={classifyMissing}
              icon={<Sparkles className="h-3.5 w-3.5" aria-hidden />}
            >
              {t("bom.classifyMissing")} ({missing.length})
            </Button>
          </>
        }
      >
        <BomTable
          product={product}
          changes={changes}
          assessments={result?.verdict.lines ?? []}
          suggestions={suggestions}
          onPatch={patch}
          onSuggest={suggest}
          onCloseSuggestion={closeSuggestion}
        />
      </Card>

      {result && (
        <div className="grid gap-4 xl:grid-cols-2">
          <CriteriaTrace verdict={result.verdict} />
          {result.verdict.reasons.length > 0 && <Reasons reasons={result.verdict.reasons} />}
        </div>
      )}
    </div>
  );
}

function BaselineChip({ baseline, current }: { baseline: Verdict; current: Verdict | null }) {
  const { t, lang } = useI18n();
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge tone={STATUS_TONE[baseline.status]} icon={<StatusIcon status={baseline.status} className="h-3 w-3" />}>
        {t("diff.was", { status: t(`verdict.status.${baseline.status}`), pct: formatPct(baseline.nom_pct, lang) })}
      </Badge>
      {current && current.status !== baseline.status && (
        <>
          <ArrowRight className="h-3.5 w-3.5 text-neutral-500" aria-hidden />
          <Badge tone={STATUS_TONE[current.status]} icon={<StatusIcon status={current.status} className="h-3 w-3" />}>
            {t(`verdict.status.${current.status}`)}
          </Badge>
        </>
      )}
    </span>
  );
}
