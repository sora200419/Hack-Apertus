// About tab: deployment architecture, AI vs deterministic split, data sources, rule pack, disclaimer.
import type { ReactNode } from "react";
import { BrainCircuit, Building2, Cloud, Cog, Library, ShieldAlert, Unplug } from "lucide-react";
import { api } from "../api";
import { useAsync } from "../hooks";
import { useI18n, type StringKey } from "../i18n";
import { formatHs, formatPct } from "../format";
import type { RulePack } from "../types";
import { Card, ErrorBox, Spinner, VerifiedBadge } from "./ui";

function Bullets({ keys }: { keys: StringKey[] }) {
  const { t } = useI18n();
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm text-neutral-800">
      {keys.map((k) => (
        <li key={k}>{t(k)}</li>
      ))}
    </ul>
  );
}

function Titled({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {icon}
      {children}
    </span>
  );
}

const ARCH: { key: StringKey; icon: ReactNode }[] = [
  { key: "about.arch.onprem", icon: <Building2 className="h-5 w-5" aria-hidden /> },
  { key: "about.arch.airgap", icon: <Unplug className="h-5 w-5" aria-hidden /> },
  { key: "about.arch.sovereign", icon: <Cloud className="h-5 w-5" aria-hidden /> },
];

export function AboutTab() {
  const { t } = useI18n();
  const pack = useAsync<RulePack>(api.rulepack);

  return (
    <div className="space-y-4">
      <Card title={t("about.title")}>
        <p className="text-sm text-neutral-800">{t("about.lead")}</p>
        <p className="mt-2 text-sm text-neutral-600">{t("about.fta")}</p>
      </Card>

      <Card title={t("about.archTitle")}>
        <ul className="grid gap-3 md:grid-cols-3">
          {ARCH.map(({ key, icon }) => (
            <li key={key} className="flex gap-3 rounded border border-neutral-200 p-3 text-sm text-neutral-800">
              <span className="text-neutral-500">{icon}</span>
              <span>{t(key)}</span>
            </li>
          ))}
        </ul>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={<Titled icon={<BrainCircuit className="h-4 w-4" aria-hidden />}>{t("about.aiTitle")}</Titled>}>
          <Bullets keys={["about.ai.hs", "about.ai.explain", "about.ai.letter"]} />
        </Card>
        <Card title={<Titled icon={<Cog className="h-4 w-4" aria-hidden />}>{t("about.detTitle")}</Titled>}>
          <Bullets keys={["about.det.verdict", "about.det.numbers", "about.det.de"]} />
        </Card>
      </div>

      <Card title={<Titled icon={<Library className="h-4 w-4" aria-hidden />}>{t("about.dataTitle")}</Titled>}>
        <Bullets keys={["about.data.hs", "about.data.fta", "about.data.tariff", "about.data.model"]} />
      </Card>

      <Card title={t("about.rulepackTitle")}>
        {pack.loading && <Spinner label={t("common.loading")} />}
        {pack.error && <ErrorBox message={pack.error} onRetry={pack.reload} />}
        {pack.data && <RulePackView pack={pack.data} />}
      </Card>

      <div role="note" className="flex items-start gap-3 rounded-lg border-2 border-accent bg-white p-4 text-sm font-medium text-neutral-900">
        <ShieldAlert className="h-5 w-5 shrink-0 text-accent" aria-hidden />
        {t("disclaimer")}
      </div>
    </div>
  );
}

function RulePackView({ pack }: { pack: RulePack }) {
  const { t, lang } = useI18n();
  const g = pack.general;
  return (
    <div className="space-y-4">
      <div className="text-sm">
        <p>
          <span className="font-mono font-semibold">{pack.pack_id}</span> · {pack.agreement}
        </p>
        <p className="text-neutral-600">{pack.version_note}</p>
      </div>
      <div>
        <h3 className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-neutral-600">
          {t("about.rulepack.general")} <VerifiedBadge verified={g.verified} />
        </h3>
        <p className="text-sm">{t("about.rulepack.tolerance", { pct: formatPct(g.tolerance_pct, lang) })} ({g.tolerance_applies_to.join(", ")})</p>
        <p className="text-xs text-neutral-600">
          {t("common.source")}: {g.source}
        </p>
      </div>
      <div className="max-h-[28rem] overflow-auto rounded border border-neutral-200">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-neutral-50 text-left text-xs text-neutral-600">
            <tr>
              <th scope="col" className="px-2 py-1.5 font-semibold">{t("about.rulepack.rule")}</th>
              <th scope="col" className="px-2 py-1.5 font-semibold">{t("about.rulepack.scope")}</th>
              <th scope="col" className="px-2 py-1.5 font-semibold">{t("about.rulepack.text")}</th>
              <th scope="col" className="px-2 py-1.5 font-semibold">{t("about.rulepack.status")}</th>
            </tr>
          </thead>
          <tbody>
            {pack.rules.map((r) => (
              <tr key={r.rule_id} className="border-t border-neutral-100 align-top">
                <td className="px-2 py-1.5 font-mono text-xs">{r.rule_id}</td>
                <td className="px-2 py-1.5 font-mono text-xs">{r.hs_scope.map((s) => (s.length === 6 ? formatHs(s) : s)).join(", ")}</td>
                <td className="px-2 py-1.5">
                  <p className="text-neutral-900">{r.text}</p>
                  <p className="text-xs text-neutral-500">{r.source}</p>
                </td>
                <td className="px-2 py-1.5">
                  <VerifiedBadge verified={r.verified} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
