// Editable bill of materials: every edit feeds the debounced re-evaluation (what-if simulator).
import { Fragment } from "react";
import { Sparkles } from "lucide-react";
import { useI18n } from "../i18n";
import { formatChf, formatPct } from "../format";
import { isChanged, type Change, type LinePatch } from "../product";
import type { LineAssessment, Product } from "../types";
import { HsSuggestPanel, type SuggestionState } from "./HsSuggestPanel";
import { HsInput, MoneyInput, OriginSelect } from "./inputs";
import { Badge, Button } from "./ui";

interface Props {
  product: Product;
  changes: Change[];
  assessments: LineAssessment[];
  suggestions: Record<string, SuggestionState>;
  onPatch: (lineId: string, patch: LinePatch) => void;
  onSuggest: (lineId: string, description: string) => void;
  onCloseSuggestion: (lineId: string) => void;
}

const COLS = 7;

export function BomTable({ product, changes, assessments, suggestions, onPatch, onSuggest, onCloseSuggestion }: Props) {
  const { t, lang } = useI18n();
  const byLine = new Map(assessments.map((a) => [a.line_id, a]));
  const total = product.bom.reduce((sum, l) => sum + l.value_chf, 0);
  const share = (v: number) => formatPct((v / product.ex_works_chf) * 100, lang);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-sm">
        <caption className="sr-only">{t("bom.title")}</caption>
        <thead>
          <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-600">
            <th scope="col" className="px-2 py-2 font-semibold">{t("bom.line")}</th>
            <th scope="col" className="px-2 py-2 font-semibold">{t("bom.description")}</th>
            <th scope="col" className="px-2 py-2 font-semibold">{t("bom.hs6")}</th>
            <th scope="col" className="px-2 py-2 font-semibold">{t("bom.origin")}</th>
            <th scope="col" className="px-2 py-2 text-right font-semibold">{t("bom.value")}</th>
            <th scope="col" className="px-2 py-2 text-right font-semibold">{t("bom.share")}</th>
            <th scope="col" className="px-2 py-2 font-semibold">{t("bom.status")}</th>
          </tr>
        </thead>
        <tbody>
          {product.bom.map((line) => {
            const a = byLine.get(line.line_id);
            const sugg = suggestions[line.line_id];
            const changed = (f: Change["field"]) => isChanged(changes, line.line_id, f);
            return (
              <Fragment key={line.line_id}>
                <tr className="border-b border-neutral-100 align-top">
                  <td className="px-2 py-2 font-mono text-xs text-neutral-600">{line.line_id}</td>
                  <td className="px-2 py-2">
                    <div className="text-neutral-900">{line.description}</div>
                    {line.supplier && <div className="text-xs text-neutral-500">{line.supplier}</div>}
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex items-center gap-1">
                      <HsInput
                        value={line.hs6}
                        changed={changed("hs6")}
                        label={`${t("bom.hs6")} ${line.line_id}`}
                        onCommit={(hs6) => onPatch(line.line_id, { hs6 })}
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={sugg?.loading}
                        onClick={() => onSuggest(line.line_id, line.description)}
                        aria-label={t("bom.suggestFor", { what: line.description })}
                        icon={<Sparkles className="h-3.5 w-3.5" aria-hidden />}
                      >
                        {t("bom.suggest")}
                      </Button>
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <OriginSelect
                      value={line.origin_country}
                      changed={changed("origin_country")}
                      label={`${t("bom.origin")} ${line.line_id}`}
                      onCommit={(origin_country) => onPatch(line.line_id, { origin_country })}
                    />
                  </td>
                  <td className="px-2 py-2 text-right">
                    <MoneyInput
                      value={line.value_chf}
                      changed={changed("value_chf")}
                      label={`${t("bom.value")} ${line.line_id}`}
                      onCommit={(value_chf) => onPatch(line.line_id, { value_chf })}
                    />
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums text-neutral-700">{share(line.value_chf)}</td>
                  <td className="px-2 py-2">
                    <LineStatus assessment={a} />
                  </td>
                </tr>
                {sugg && (
                  <tr className="border-b border-neutral-100">
                    <td colSpan={COLS} className="px-2 pb-3">
                      <HsSuggestPanel
                        subject={line.description}
                        state={sugg}
                        current={line.hs6}
                        onAccept={(hs6) => onPatch(line.line_id, { hs6 })}
                        onRetry={() => onSuggest(line.line_id, line.description)}
                        onClose={() => onCloseSuggestion(line.line_id)}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="text-sm font-semibold">
            <td colSpan={4} className="px-2 py-2 text-right text-neutral-700">{t("bom.total")}</td>
            <td className="px-2 py-2 text-right tabular-nums">{formatChf(total, lang)}</td>
            <td className="px-2 py-2 text-right tabular-nums">{share(total)}</td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function LineStatus({ assessment: a }: { assessment: LineAssessment | undefined }) {
  const { t } = useI18n();
  if (!a) return <span className="text-neutral-400">—</span>;
  return (
    <div className="space-y-0.5" title={a.reason}>
      <Badge tone={a.originating ? "green" : "neutral"}>{t(a.originating ? "bom.originating" : "bom.nonOriginating")}</Badge>
      {a.shift_ok !== null && (
        <div className={`text-xs ${a.shift_ok ? "text-emerald-800" : "text-red-700"}`}>
          {a.shift_ok ? "✓ " : "✗ "}
          {t(a.shift_ok ? "bom.shiftOk" : "bom.shiftFail")}
        </div>
      )}
      <p className="line-clamp-2 max-w-[14rem] text-[11px] text-neutral-500">{a.reason}</p>
    </div>
  );
}
