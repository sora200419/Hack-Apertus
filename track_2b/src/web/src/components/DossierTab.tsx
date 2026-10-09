// Dossier tab: Apertus-drafted texts with fact checks, checklist and duty estimate.
import { useState } from "react";
import { Check, ClipboardCopy, Download, FileText, X } from "lucide-react";
import { api, errorMessage } from "../api";
import { useI18n, type StringKey, type Translate } from "../i18n";
import type { Dossier, DossierText, Product } from "../types";
import { DutyCard } from "./DutyCard";
import { Badge, Button, Card, ErrorBox, Notice, STATUS_TONE, SourceBadge, Spinner, StatusIcon } from "./ui";

const TEXTS: { key: "explanation_en" | "explanation_de" | "letter_zh" | "back_translation_en"; title: StringKey; lang: string }[] = [
  { key: "explanation_en", title: "dossier.explanationEn", lang: "en" },
  { key: "explanation_de", title: "dossier.explanationDe", lang: "de-CH" },
  { key: "letter_zh", title: "dossier.letterZh", lang: "zh-Hans" },
  { key: "back_translation_en", title: "dossier.backTranslation", lang: "en" },
];

export function DossierTab({ product }: { product: Product }) {
  const { t } = useI18n();
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [generatedFor, setGeneratedFor] = useState<Product | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Set<number>>(new Set());

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      const d = await api.dossier(product);
      setDossier(d);
      setGeneratedFor(product);
      setDone(new Set());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  function toggle(i: number) {
    setDone((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      <Card
        title={t("tab.dossier")}
        actions={
          <>
            {dossier && (
              <Button size="sm" onClick={() => download(product, dossier, t)} icon={<Download className="h-3.5 w-3.5" aria-hidden />}>
                {t("dossier.download")}
              </Button>
            )}
            <Button variant="primary" loading={loading} onClick={generate} icon={<FileText className="h-4 w-4" aria-hidden />}>
              {dossier ? t("dossier.regenerate") : t("dossier.generate")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-neutral-700">{t("dossier.intro")}</p>
        {loading && (
          <div className="mt-3">
            <Spinner label={t("dossier.generating")} />
          </div>
        )}
        {error && (
          <div className="mt-3">
            <ErrorBox message={error} onRetry={generate} />
          </div>
        )}
        {dossier && generatedFor !== product && (
          <div className="mt-3">
            <Notice>{t("dossier.stale")}</Notice>
          </div>
        )}
        {dossier && (
          <p className="mt-3 flex items-center gap-2 text-sm">
            {t("dossier.verdict")}:
            <Badge tone={STATUS_TONE[dossier.verdict_status]} icon={<StatusIcon status={dossier.verdict_status} className="h-3 w-3" />}>
              {t(`verdict.status.${dossier.verdict_status}`)}
            </Badge>
          </p>
        )}
      </Card>

      {dossier && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            {TEXTS.map(({ key, title, lang }) => (
              <TextCard key={key} title={t(title)} text={dossier[key]} lang={lang} />
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title={t("dossier.checklist")} actions={<span className="text-xs text-neutral-600">{t("dossier.checklistDone", { done: done.size, total: dossier.checklist.length })}</span>}>
              <ul className="space-y-2">
                {dossier.checklist.map((item, i) => (
                  <li key={i}>
                    <label className="flex cursor-pointer items-start gap-2 text-sm text-neutral-800">
                      <input type="checkbox" checked={done.has(i)} onChange={() => toggle(i)} className="mt-0.5 h-4 w-4 accent-neutral-900" />
                      <span className={done.has(i) ? "text-neutral-500 line-through" : ""}>{item}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </Card>
            <DutyCard duty={dossier.duty} hs6={generatedFor?.hs6 ?? null} />
          </div>
        </>
      )}
    </div>
  );
}

function TextCard({ title, text, lang }: { title: string; text: DossierText; lang: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const found = text.fact_checks.filter((f) => f.found).length;

  async function copy() {
    try {
      await navigator.clipboard.writeText(text.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Card
      title={title}
      actions={
        <>
          <SourceBadge source={text.llm_source} />
          {text.attempts > 1 && <Badge tone="neutral">{t("dossier.attempts", { n: text.attempts })}</Badge>}
          <Button size="sm" variant="ghost" onClick={copy} icon={copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <ClipboardCopy className="h-3.5 w-3.5" aria-hidden />}>
            {copied ? t("common.copied") : t("common.copy")}
          </Button>
        </>
      }
      className="flex flex-col"
    >
      <div lang={lang} className="whitespace-pre-wrap text-sm leading-relaxed text-neutral-900">
        {text.text}
      </div>
      {text.fact_checks.length > 0 && (
        <div className="mt-4 border-t border-neutral-100 pt-3">
          <div className="mb-1.5 text-xs font-semibold text-neutral-600">
            {t("dossier.facts", { found, total: text.fact_checks.length })}
          </div>
          <ul className="flex flex-wrap gap-1.5">
            {text.fact_checks.map((f, i) => (
              <li key={i}>
                <Badge
                  tone={f.found ? "green" : "red"}
                  icon={f.found ? <Check className="h-3 w-3" aria-hidden /> : <X className="h-3 w-3" aria-hidden />}
                >
                  <span className="sr-only">{f.found ? t("trace.passed") : t("trace.failed")}: </span>
                  {f.fact}: <span className="font-mono">{f.expected}</span>
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

/** Save the dossier as a plain-text file. */
function download(product: Product, d: Dossier, t: Translate) {
  const parts = [
    `OriginPass CH–CN · ${product.name} (${product.product_id})`,
    `${t("dossier.verdict")}: ${d.verdict_status}`,
    ...TEXTS.map(({ key, title }) => `== ${t(title)} [${d[key].llm_source}] ==\n${d[key].text}`),
    `== ${t("dossier.checklist")} ==\n${d.checklist.map((c) => `[ ] ${c}`).join("\n")}`,
    t("disclaimer"),
  ];
  const url = URL.createObjectURL(new Blob([parts.join("\n\n") + "\n"], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `originpass-${product.product_id}-dossier.txt`;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
