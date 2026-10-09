// PRC import duty estimate; unknown rates are labelled "rate not verified", never guessed.
import { Coins } from "lucide-react";
import { useI18n } from "../i18n";
import { formatChf, formatHs, formatPct } from "../format";
import type { DutyEstimate } from "../types";
import { Badge, Card } from "./ui";

/** `hs6` is the product code the estimate was requested for; null explains a missing estimate. */
export function DutyCard({ duty, hs6 }: { duty: DutyEstimate | null; hs6: string | null }) {
  const { t, lang } = useI18n();
  const unverified = <Badge tone="amber">{t("duty.notVerified")}</Badge>;
  const rate = (v: number | null) => (v === null ? unverified : formatPct(v, lang, 1));

  return (
    <Card title={<span className="inline-flex items-center gap-1.5"><Coins className="h-4 w-4" aria-hidden />{t("duty.title")}</span>}>
      {duty === null ? (
        <p className="text-sm text-neutral-600">{hs6 ? t("duty.noRate", { hs: formatHs(hs6) }) : t("duty.none")}</p>
      ) : (
        <>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
            <dt className="text-neutral-600">HS6</dt>
            <dd className="font-mono">{formatHs(duty.hs6)}</dd>
            <dt className="text-neutral-600">{t("duty.mfn")}</dt>
            <dd>{rate(duty.mfn_rate_pct)}</dd>
            <dt className="text-neutral-600">{t("duty.fta")}</dt>
            <dd>{rate(duty.fta_rate_pct)}</dd>
            <dt className="text-neutral-600">{t("duty.order")}</dt>
            <dd className="tabular-nums">{formatChf(duty.order_value_chf, lang)}</dd>
            <dt className="font-semibold text-neutral-900">{t("duty.saved")}</dt>
            <dd className="font-semibold tabular-nums">
              {duty.duty_saved_chf === null ? unverified : formatChf(duty.duty_saved_chf, lang)}
            </dd>
          </dl>
          <details className="mt-3 text-xs text-neutral-600">
            <summary className="cursor-pointer select-none">{t("common.source")}</summary>
            <p className="mt-1">{duty.source}</p>
          </details>
        </>
      )}
    </Card>
  );
}
