// Verdict display: status, quoted rule, NOM gauge, criteria trace, reasoning and fixes.
import { Lightbulb, ListOrdered, Scale } from "lucide-react";
import { useI18n } from "../i18n";
import { formatChf, formatHs, formatPct, formatPp } from "../format";
import type { CheckResult, Criterion, Verdict, VerdictStatus } from "../types";
import { Badge, Card, CheckBadge, StatusIcon, VerifiedBadge } from "./ui";

const STATUS_PANEL: Record<VerdictStatus, string> = {
  PASS: "bg-emerald-50 text-emerald-900 border-emerald-600",
  FAIL: "bg-red-50 text-red-900 border-red-600",
  UNSURE: "bg-amber-50 text-amber-900 border-amber-500",
};

export function VerdictSummary({ verdict }: { verdict: Verdict }) {
  const { t } = useI18n();
  const { status, rule } = verdict;
  return (
    <section aria-labelledby="verdict-status" className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
      <div className="grid md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className={`border-l-8 p-5 ${STATUS_PANEL[status]}`}>
          <div className="flex items-center gap-3">
            <StatusIcon status={status} className="h-10 w-10 shrink-0" />
            <div>
              <p id="verdict-status" className="text-3xl font-bold tracking-tight">
                {t(`verdict.status.${status}`)}
              </p>
              <p className="text-sm">{t(`verdict.sub.${status}`)}</p>
            </div>
          </div>
          <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm">
            <div>
              <dt className="inline opacity-75">{t("verdict.productHs")}: </dt>
              <dd className="inline font-mono font-semibold">{formatHs(verdict.hs6)}</dd>
            </div>
            {rule && (
              <div>
                <dt className="sr-only">{t("verdict.rule")}</dt>
                <dd className="inline font-mono">{rule.rule_id}</dd>
              </div>
            )}
          </dl>
          {verdict.tolerance_used && (
            <div className="mt-2">
              <Badge tone="neutral">{t("verdict.toleranceUsed")}</Badge>
            </div>
          )}
        </div>
        <div className="p-5">
          <NomGauge verdict={verdict} />
        </div>
      </div>

      <div className="border-t border-neutral-200 p-5">
        {rule ? (
          <figure>
            <figcaption className="mb-2 flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wide text-neutral-600">
              <Scale className="h-4 w-4" aria-hidden />
              {t("verdict.rule")}
              <span className="font-mono normal-case text-neutral-900">{rule.rule_id}</span>
              <VerifiedBadge verified={verdict.rule_verified} />
            </figcaption>
            <blockquote className="border-l-4 border-neutral-300 pl-3 text-sm italic text-neutral-900">“{rule.text}”</blockquote>
            {rule.text_zh && (
              <blockquote lang="zh-Hans" className="mt-2 border-l-4 border-neutral-200 pl-3 text-sm text-neutral-700">
                {rule.text_zh}
              </blockquote>
            )}
            <p className="mt-2 text-xs text-neutral-600">
              {t("common.source")}: {rule.source}
            </p>
            {!verdict.rule_verified && <p className="mt-1 text-xs text-amber-800">{t("verdict.ruleUnverifiedHint")}</p>}
          </figure>
        ) : (
          <p className="text-sm text-neutral-700">{t("verdict.noRule")}</p>
        )}
      </div>
    </section>
  );
}

function NomGauge({ verdict }: { verdict: Verdict }) {
  const { t, lang } = useI18n();
  const { nom_pct: nom, threshold_pct: threshold, margin_pct: margin } = verdict;
  const max = Math.max(100, nom, threshold ?? 0);
  const pos = (v: number) => `${Math.min(100, (v / max) * 100)}%`;
  const fill = threshold === null ? "bg-neutral-500" : nom <= threshold ? "bg-emerald-600" : "bg-red-600";

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-600">{t("gauge.title")}</h3>
      <div className="relative mt-7">
        <div
          role="meter"
          aria-valuemin={0}
          aria-valuemax={max}
          aria-valuenow={nom}
          aria-label={t("gauge.aria", {
            pct: formatPct(nom, lang),
            threshold: threshold === null ? "—" : formatPct(threshold, lang),
          })}
          className="relative h-5 overflow-hidden rounded bg-neutral-100 ring-1 ring-inset ring-neutral-200"
        >
          <div className={`h-full transition-[width] duration-300 ${fill}`} style={{ width: pos(nom) }} />
        </div>
        {threshold !== null && (
          <div className="absolute -bottom-1 -top-1 w-0.5 bg-neutral-900" style={{ left: pos(threshold) }} aria-hidden>
            <span className="absolute -top-5 -translate-x-1/2 whitespace-nowrap text-xs font-semibold text-neutral-900">
              {formatPct(threshold, lang, 0)}
            </span>
          </div>
        )}
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-neutral-500" aria-hidden>
        <span>0%</span>
        <span>{formatPct(max / 2, lang, 0)}</span>
        <span>{formatPct(max, lang, 0)}</span>
      </div>
      <p className="mt-3 text-sm text-neutral-900">
        {t("gauge.nom", { pct: formatPct(nom, lang), chf: formatChf(verdict.nom_value_chf, lang) })}
      </p>
      {threshold !== null ? (
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm">
          <span>{t("gauge.threshold", { pct: formatPct(threshold, lang) })}</span>
          {margin !== null && (
            <Badge tone={margin >= 0 ? "green" : "red"}>
              {t(margin >= 0 ? "gauge.headroom" : "gauge.over", { pp: formatPp(margin, lang) })}
            </Badge>
          )}
        </p>
      ) : (
        <p className="mt-1 text-xs text-neutral-600">{t("gauge.noThreshold")}</p>
      )}
    </div>
  );
}

function criterionLabel(c: Criterion, exceptWord: string): string {
  if (c.kind === "MAXNOM") return `MAXNOM ≤ ${c.max_nom_pct ?? "?"}%`;
  if (c.except_from.length) return `${c.kind} (${exceptWord} ${c.except_from.map(formatPrefix).join(", ")})`;
  return c.kind;
}

/** HS prefix '9114' -> '91.14', '841370' -> '8413.70'. */
function formatPrefix(p: string): string {
  if (p.length === 4) return `${p.slice(0, 2)}.${p.slice(2)}`;
  return formatHs(p);
}

export function CriteriaTrace({ verdict }: { verdict: Verdict }) {
  const { t } = useI18n();
  const metLabels: [string, string, string] = [t("trace.met"), t("trace.notMet"), t("trace.undecided")];
  return (
    <Card title={t("trace.title")}>
      <p className="mb-3 text-xs text-neutral-600">{t("trace.hint")}</p>
      {verdict.alternatives.length === 0 && verdict.general_checks.length === 0 && (
        <p className="text-sm text-neutral-600">{t("trace.none")}</p>
      )}
      <ol className="space-y-3">
        {verdict.alternatives.map((alt, i) => (
          <li key={i} className="rounded border border-neutral-200">
            <div className="flex flex-wrap items-center gap-2 border-b border-neutral-100 bg-neutral-50 px-3 py-2">
              <span className="text-sm font-semibold">{t("trace.alternative", { n: i + 1 })}</span>
              {alt.criteria.map((c, j) => (
                <span key={j} title={c.note ?? undefined} className="rounded bg-white px-1.5 py-0.5 font-mono text-xs ring-1 ring-neutral-300">
                  {criterionLabel(c, t("trace.except"))}
                </span>
              ))}
              <span className="ml-auto">
                <CheckBadge passed={alt.met} labels={metLabels} />
              </span>
            </div>
            <CheckList checks={alt.checks} />
          </li>
        ))}
      </ol>
      {verdict.general_checks.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-neutral-600">{t("trace.general")}</h3>
          <div className="rounded border border-neutral-200">
            <CheckList checks={verdict.general_checks} />
          </div>
        </div>
      )}
    </Card>
  );
}

function CheckList({ checks }: { checks: CheckResult[] }) {
  const { t } = useI18n();
  const labels: [string, string, string] = [t("trace.passed"), t("trace.failed"), t("trace.undecided")];
  return (
    <ul className="divide-y divide-neutral-100">
      {checks.map((c, i) => (
        <li key={i} className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 px-3 py-2 text-sm">
          <CheckBadge passed={c.passed} labels={labels} />
          <div>
            <span className="font-medium text-neutral-900">{c.name}</span>
            <p className="text-neutral-700">{c.detail}</p>
            {c.line_ids.length > 0 && (
              <p className="mt-1 flex flex-wrap items-center gap-1 text-xs text-neutral-600">
                {t("trace.lines")}:
                {c.line_ids.map((id) => (
                  <span key={id} className="rounded bg-neutral-100 px-1 font-mono">
                    {id}
                  </span>
                ))}
              </p>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Reasons({ reasons }: { reasons: string[] }) {
  const { t } = useI18n();
  return (
    <Card title={<span className="inline-flex items-center gap-1.5"><ListOrdered className="h-4 w-4" aria-hidden />{t("verdict.reasons")}</span>}>
      <ol className="list-decimal space-y-1 pl-5 text-sm text-neutral-800">
        {reasons.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ol>
    </Card>
  );
}

export function Fixes({ fixes }: { fixes: string[] }) {
  const { t } = useI18n();
  return (
    <Card title={<span className="inline-flex items-center gap-1.5"><Lightbulb className="h-4 w-4" aria-hidden />{t("fixes.title")}</span>}>
      {fixes.length === 0 ? (
        <p className="text-sm text-neutral-600">{t("fixes.none")}</p>
      ) : (
        <ul className="space-y-2 text-sm text-neutral-800">
          {fixes.map((f, i) => (
            <li key={i} className="flex gap-2">
              <span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
              {f}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
