// App shell: header, product panel, tabs; owns the loaded product and its live evaluation.
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { FileText, FlaskConical, Info, Scale } from "lucide-react";
import { api, errorMessage } from "./api";
import { useAsync, useDebouncedEvaluation } from "./hooks";
import { I18nContext, makeT, type Lang, type StringKey } from "./i18n";
import type { Product, Verdict } from "./types";
import { AboutTab } from "./components/AboutTab";
import { DossierTab } from "./components/DossierTab";
import { EvalTab } from "./components/EvalTab";
import { Header } from "./components/Header";
import { ProductPanel } from "./components/ProductPanel";
import { VerdictTab } from "./components/VerdictTab";
import { ErrorBox } from "./components/ui";

type TabId = "verdict" | "dossier" | "eval" | "about";
const TABS: { id: TabId; label: StringKey; icon: ReactNode }[] = [
  { id: "verdict", label: "tab.verdict", icon: <Scale className="h-4 w-4" aria-hidden /> },
  { id: "dossier", label: "tab.dossier", icon: <FileText className="h-4 w-4" aria-hidden /> },
  { id: "eval", label: "tab.eval", icon: <FlaskConical className="h-4 w-4" aria-hidden /> },
  { id: "about", label: "tab.about", icon: <Info className="h-4 w-4" aria-hidden /> },
];

const LANG_KEY = "originpass.lang";
const HTML_LANG: Record<Lang, string> = { en: "en", de: "de-CH", zh: "zh-Hans" };

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved === "en" || saved === "de" || saved === "zh") return saved;
  } catch {
    // storage unavailable (private mode): fall through
  }
  const nav = navigator.language.toLowerCase();
  return nav.startsWith("de") ? "de" : nav.startsWith("zh") ? "zh" : "en";
}

export default function App() {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(LANG_KEY, l);
    } catch {
      // not persisted; the choice still applies for this visit
    }
  }, []);
  const i18n = useMemo(() => ({ lang, setLang, t: makeT(lang) }), [lang, setLang]);
  const { t } = i18n;
  useEffect(() => {
    document.documentElement.lang = HTML_LANG[lang];
  }, [lang]);

  const health = useAsync(api.health);
  const products = useAsync(api.products);

  // Tab panels mount on first visit and then stay mounted, so their state survives tab switches.
  const [tab, setTab] = useState<TabId>("verdict");
  const [visited, setVisited] = useState<Set<TabId>>(new Set(["verdict"]));
  const selectTab = useCallback((id: TabId) => {
    setTab(id);
    setVisited((v) => (v.has(id) ? v : new Set(v).add(id)));
  }, []);

  const [original, setOriginal] = useState<Product | null>(null);
  const [product, setProduct] = useState<Product | null>(null);
  const [loadKey, setLoadKey] = useState(0);
  const [baseline, setBaseline] = useState<Verdict | null>(null);
  const [autoError, setAutoError] = useState<string | null>(null);
  const evaluation = useDebouncedEvaluation(product, loadKey);

  const load = useCallback((p: Product) => {
    setOriginal(p);
    setProduct(p);
    setBaseline(null);
    setLoadKey((k) => k + 1);
    selectTab("verdict");
  }, [selectTab]);

  // The verdict of the unedited product is the baseline for the what-if comparison.
  useEffect(() => {
    if (evaluation.result && evaluation.evaluated === original) setBaseline(evaluation.result.verdict);
  }, [evaluation, original]);

  // Open the first demo product so the first screen is never empty (unless the user was faster).
  const autoLoaded = useRef(false);
  const productRef = useRef(product);
  productRef.current = product;
  useEffect(() => {
    const first = products.data?.[0];
    if (!first || autoLoaded.current) return;
    autoLoaded.current = true;
    api.product(first.product_id).then(
      (p) => {
        if (!productRef.current) load(p);
      },
      (err) => setAutoError(errorMessage(err)),
    );
  }, [products.data, load]);

  const update = useCallback((fn: (p: Product) => Product) => setProduct((p) => (p ? fn(p) : p)), []);
  const reset = useCallback(() => setProduct(original), [original]);

  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onTabKey(e: KeyboardEvent) {
    const i = TABS.findIndex((x) => x.id === tab);
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    const next = TABS[(i + step + TABS.length) % TABS.length].id;
    selectTab(next);
    tabRefs.current[next]?.focus();
  }

  const empty = (
    <div className="rounded-lg border border-dashed border-neutral-300 bg-white p-10 text-center text-sm text-neutral-600">
      {autoError ? <ErrorBox message={autoError} /> : t("verdict.empty")}
    </div>
  );

  return (
    <I18nContext.Provider value={i18n}>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:bg-white focus:p-2">
        {t("app.skip")}
      </a>
      <div className="flex min-h-screen flex-col">
        <Header health={health} />
        <div className="mx-auto grid w-full max-w-[1440px] flex-1 gap-6 px-4 py-6 lg:grid-cols-[300px_minmax(0,1fr)] lg:px-6">
          <aside className="order-2 lg:order-1">
            <ProductPanel products={products} currentId={original?.product_id ?? null} onLoad={load} />
          </aside>
          <main id="main" className="order-1 min-w-0 lg:order-2">
            <div role="tablist" aria-label="OriginPass" className="mb-4 flex gap-1 overflow-x-auto border-b border-neutral-200" onKeyDown={onTabKey}>
              {TABS.map(({ id, label, icon }) => (
                <button
                  key={id}
                  ref={(el) => {
                    tabRefs.current[id] = el;
                  }}
                  id={`tab-${id}`}
                  type="button"
                  role="tab"
                  aria-selected={tab === id}
                  aria-controls={`panel-${id}`}
                  tabIndex={tab === id ? 0 : -1}
                  onClick={() => selectTab(id)}
                  className={`-mb-px inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
                    tab === id ? "border-accent text-neutral-900" : "border-transparent text-neutral-600 hover:text-neutral-900"
                  }`}
                >
                  {icon}
                  {t(label)}
                </button>
              ))}
            </div>

            {TABS.filter(({ id }) => visited.has(id)).map(({ id }) => (
              <div key={id} id={`panel-${id}`} role="tabpanel" aria-labelledby={`tab-${id}`} hidden={tab !== id}>
                {id === "verdict" &&
                  (product && original ? (
                    <VerdictTab
                      key={loadKey}
                      product={product}
                      original={original}
                      onChange={update}
                      onReset={reset}
                      evaluation={evaluation}
                      baseline={baseline}
                    />
                  ) : (
                    empty
                  ))}
                {id === "dossier" && (product ? <DossierTab key={loadKey} product={product} /> : empty)}
                {id === "eval" && <EvalTab />}
                {id === "about" && <AboutTab />}
              </div>
            ))}
          </main>
        </div>
        <footer className="border-t border-neutral-200 bg-white">
          <p className="mx-auto max-w-[1440px] px-4 py-3 text-xs text-neutral-600 lg:px-6">
            {t("disclaimer")} · Hack Apertus 2026 · Track 2B
          </p>
        </footer>
      </div>
    </I18nContext.Provider>
  );
}
