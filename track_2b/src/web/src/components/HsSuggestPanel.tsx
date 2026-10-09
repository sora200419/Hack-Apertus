// Shows one HS classification: retrieved candidates, Apertus choice, confidence, rationale, provenance.
import { Check, Sparkles, X } from "lucide-react";
import { useI18n } from "../i18n";
import { formatHs, formatNumber } from "../format";
import type { HSSuggestion } from "../types";
import { Badge, Button, ErrorBox, Notice, SourceBadge, Spinner } from "./ui";

export interface SuggestionState {
  loading: boolean;
  error: string | null;
  data: HSSuggestion | null;
}

/** A suggestion that may be applied without review: the model chose a code and did not abstain. */
export const isConfident = (s: SuggestionState | undefined): s is SuggestionState & { data: HSSuggestion & { chosen: string } } =>
  !!s?.data && !s.data.abstained && s.data.chosen !== null;

interface Props {
  subject: string;
  state: SuggestionState;
  current: string | null;
  onAccept: (hs6: string) => void;
  onRetry: () => void;
  onClose: () => void;
}

export function HsSuggestPanel({ subject, state, current, onAccept, onRetry, onClose }: Props) {
  const { t, lang } = useI18n();
  const s = state.data;
  const chosen = s?.chosen ? s.candidates.find((c) => c.hs6 === s.chosen) : undefined;

  return (
    <div className="rounded border border-neutral-300 bg-neutral-50 p-3" aria-live="polite">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Sparkles className="h-4 w-4 text-neutral-600" aria-hidden />
        <span className="text-sm font-semibold">{t("hs.title")}</span>
        <span className="truncate text-sm text-neutral-600">
          {t("hs.for")} “{subject}”
        </span>
        {s && (
          <>
            <Badge tone="neutral">{t(`hs.method.${s.method}`)}</Badge>
            <SourceBadge source={s.llm_source} />
          </>
        )}
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onClose} aria-label={t("common.close")} icon={<X className="h-3.5 w-3.5" aria-hidden />} />
      </div>

      {state.loading && <Spinner label={t("common.loading")} />}
      {state.error && <ErrorBox message={state.error} onRetry={onRetry} />}

      {s && (
        <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className="space-y-2">
            {s.abstained || !s.chosen ? (
              <Notice>{t("hs.abstained")}</Notice>
            ) : (
              <div className="rounded border border-neutral-200 bg-white p-2">
                <div className="text-xs text-neutral-600">{t("hs.chosen")}</div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-lg font-semibold">{formatHs(s.chosen)}</span>
                  {s.chosen === current ? (
                    <Badge tone="green" icon={<Check className="h-3 w-3" aria-hidden />}>{t("hs.current")}</Badge>
                  ) : (
                    <Button size="sm" variant="primary" onClick={() => onAccept(s.chosen as string)} icon={<Check className="h-3.5 w-3.5" aria-hidden />}>
                      {t("hs.accept")}
                    </Button>
                  )}
                </div>
                {chosen && <p className="text-xs text-neutral-700">{chosen.description}</p>}
              </div>
            )}
            <div>
              <div className="flex justify-between text-xs text-neutral-600">
                <span>{t("hs.confidence")}</span>
                <span className="tabular-nums">{formatNumber(s.confidence * 100, lang, 0)}%</span>
              </div>
              <div className="mt-0.5 h-1.5 rounded bg-neutral-200" aria-hidden>
                <div className="h-full rounded bg-neutral-800" style={{ width: `${s.confidence * 100}%` }} />
              </div>
            </div>
            {s.rationale && (
              <div className="text-xs text-neutral-700">
                <span className="font-semibold">{t("hs.rationale")}: </span>
                {s.rationale}
              </div>
            )}
          </div>

          <div>
            <div className="mb-1 text-xs font-semibold text-neutral-600">{t("hs.candidates")}</div>
            <ol className="max-h-56 divide-y divide-neutral-200 overflow-y-auto rounded border border-neutral-200 bg-white text-xs">
              {s.candidates.map((c) => (
                <li key={c.hs6} className={`flex items-center gap-2 px-2 py-1.5 ${c.hs6 === s.chosen ? "bg-emerald-50" : ""}`}>
                  <span className="w-16 shrink-0 font-mono font-semibold">{formatHs(c.hs6)}</span>
                  <span className="flex-1 text-neutral-800">{c.description}</span>
                  <span className="shrink-0 tabular-nums text-neutral-500" title={c.source}>
                    {t("hs.score")} {formatNumber(c.score, lang, 2)}
                  </span>
                  {c.hs6 !== current && (
                    <Button size="sm" variant="ghost" onClick={() => onAccept(c.hs6)} aria-label={`${t("hs.use")} ${formatHs(c.hs6)}`}>
                      {t("hs.use")}
                    </Button>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}
