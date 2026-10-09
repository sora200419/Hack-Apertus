// App header: brand, LLM mode, models, rule-pack verification status and language toggle.
import { AlertTriangle, BookCheck, Cpu, Database, Radio, WifiOff } from "lucide-react";
import { LANGS, useI18n } from "../i18n";
import type { AsyncState } from "../hooks";
import type { Health } from "../types";
import { Badge } from "./ui";

export function Header({ health }: { health: AsyncState<Health> }) {
  const { t, lang, setLang } = useI18n();
  const h = health.data;

  return (
    <header className="border-b border-neutral-200 bg-white">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 lg:px-6">
        <div className="flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="h-8 w-8" />
          <div>
            <h1 className="text-lg font-bold leading-tight tracking-tight text-neutral-900">OriginPass CH–CN</h1>
            <p className="text-xs text-neutral-600">{t("app.tagline")}</p>
          </div>
        </div>

        <div className="flex flex-1 flex-wrap items-center gap-2" aria-live="polite">
          {health.error && (
            <button type="button" onClick={health.reload} title={health.error}>
              <Badge tone="red" icon={<WifiOff className="h-3 w-3" aria-hidden />}>
                {t("mode.offline")} · {t("common.retry")}
              </Badge>
            </button>
          )}
          {h && (
            <>
              {h.mode === "replay" ? (
                <Badge
                  tone="neutral"
                  icon={<Database className="h-3 w-3" aria-hidden />}
                  title={t("mode.replayHint", { n: h.replay_entries })}
                >
                  {t("mode.replay")}
                </Badge>
              ) : (
                <Badge
                  tone="dark"
                  icon={<Radio className="h-3 w-3" aria-hidden />}
                  title={t("mode.liveHint", { host: h.base_url_host ?? "?" })}
                >
                  {t(h.mode === "record" ? "mode.record" : "mode.live")}
                </Badge>
              )}
              <Badge tone="neutral" icon={<Cpu className="h-3 w-3" aria-hidden />} title={t("header.models")}>
                <span className="font-mono">
                  {shortModel(h.llm_name)}
                  {h.llm_name_small && h.llm_name_small !== h.llm_name ? ` / ${shortModel(h.llm_name_small)}` : ""}
                </span>
              </Badge>
              <RulepackBadge {...h.rulepack} />
            </>
          )}
        </div>

        <div role="group" aria-label={t("app.language")} className="flex rounded border border-neutral-300 text-xs">
          {LANGS.map((l) => (
            <button
              key={l.code}
              type="button"
              lang={l.code}
              aria-pressed={lang === l.code}
              onClick={() => setLang(l.code)}
              className={`px-2.5 py-1 font-medium first:rounded-l last:rounded-r ${
                lang === l.code ? "bg-neutral-900 text-white" : "text-neutral-700 hover:bg-neutral-100"
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}

function RulepackBadge({ pack_id, rules, verified_rules }: Health["rulepack"]) {
  const { t } = useI18n();
  const all = rules > 0 && verified_rules === rules;
  return (
    <Badge
      tone={all ? "green" : "amber"}
      icon={all ? <BookCheck className="h-3 w-3" aria-hidden /> : <AlertTriangle className="h-3 w-3" aria-hidden />}
      title={all ? undefined : t("header.rulesUnverifiedHint")}
    >
      <span className="font-mono">{pack_id}</span> · {t("header.rulesVerified", { v: verified_rules, n: rules })}
    </Badge>
  );
}

/** 'swiss-ai/Apertus-v1.5-70B' -> 'Apertus-v1.5-70B'. */
function shortModel(name: string): string {
  return name.split("/").pop() ?? name;
}
