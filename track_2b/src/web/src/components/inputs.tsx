// Draft-and-commit inputs for the what-if simulator: a value is committed only once it is valid,
// so partially typed codes never reach the engine.
import { useEffect, useState } from "react";
import { HS6_RE, ISO2_RE, KNOWN_ORIGINS } from "../product";
import { useI18n } from "../i18n";

const CHANGED = "bg-amber-50 border-amber-400";
const BASE = "rounded border px-2 py-1 text-sm focus:border-neutral-900";

const normaliseHs = (s: string) => s.replace(/\D/g, "");

export function HsInput({
  value,
  onCommit,
  label,
  changed,
}: {
  value: string | null;
  onCommit: (hs6: string | null) => void;
  label: string;
  changed: boolean;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState(value ?? "");
  useEffect(() => {
    setDraft((d) => (normaliseHs(d) === (value ?? "") ? d : (value ?? "")));
  }, [value]);

  const digits = normaliseHs(draft);
  const valid = digits === "" || HS6_RE.test(digits);

  function change(next: string) {
    setDraft(next);
    const d = normaliseHs(next);
    if (d === "") {
      if (value !== null) onCommit(null);
    } else if (HS6_RE.test(d) && d !== value) onCommit(d);
  }

  return (
    <input
      value={draft}
      onChange={(e) => change(e.target.value)}
      inputMode="numeric"
      maxLength={7}
      placeholder="HS6"
      aria-label={label}
      aria-invalid={!valid}
      title={valid ? undefined : t("form.invalidHs")}
      className={`${BASE} w-[5.5rem] font-mono ${!valid ? "border-red-500 bg-red-50" : changed ? CHANGED : "border-neutral-300"}`}
    />
  );
}

export function MoneyInput({
  value,
  onCommit,
  label,
  changed,
  allowZero = true,
}: {
  value: number;
  onCommit: (v: number) => void;
  label: string;
  changed: boolean;
  allowZero?: boolean;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState(String(value));
  useEffect(() => {
    setDraft((d) => (Number(d) === value ? d : String(value)));
  }, [value]);

  const n = Number(draft);
  const valid = draft.trim() !== "" && Number.isFinite(n) && (allowZero ? n >= 0 : n > 0);

  function change(next: string) {
    setDraft(next);
    const v = Number(next);
    if (next.trim() !== "" && Number.isFinite(v) && (allowZero ? v >= 0 : v > 0) && v !== value) onCommit(v);
  }

  return (
    <input
      type="number"
      min={0}
      step="0.01"
      inputMode="decimal"
      value={draft}
      onChange={(e) => change(e.target.value)}
      aria-label={label}
      aria-invalid={!valid}
      title={valid ? undefined : t("form.invalidPrice")}
      className={`${BASE} w-28 text-right tabular-nums ${!valid ? "border-red-500 bg-red-50" : changed ? CHANGED : "border-neutral-300"}`}
    />
  );
}

const OTHER = "__other";

export function OriginSelect({
  value,
  onCommit,
  label,
  changed,
}: {
  value: string;
  onCommit: (iso2: string) => void;
  label: string;
  changed: boolean;
}) {
  const { t } = useI18n();
  const known = (KNOWN_ORIGINS as readonly string[]).includes(value);
  const [other, setOther] = useState(!known);
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    setOther(!(KNOWN_ORIGINS as readonly string[]).includes(value));
    setDraft(value);
  }, [value]);

  function select(next: string) {
    if (next === OTHER) {
      setOther(true);
      setDraft("");
    } else {
      setOther(false);
      if (next !== value) onCommit(next);
    }
  }

  function type(next: string) {
    const code = next.toUpperCase().slice(0, 2);
    setDraft(code);
    if (ISO2_RE.test(code) && code !== value) onCommit(code);
  }

  const tone = changed ? CHANGED : "border-neutral-300";
  return (
    <div className="flex items-center gap-1">
      <select
        value={other ? OTHER : value}
        onChange={(e) => select(e.target.value)}
        aria-label={label}
        className={`${BASE} bg-white ${tone}`}
      >
        {KNOWN_ORIGINS.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
        <option value={OTHER}>{t("bom.other")}</option>
      </select>
      {other && (
        <input
          value={draft}
          onChange={(e) => type(e.target.value)}
          aria-label={`${label} – ${t("bom.otherCode")}`}
          placeholder="XX"
          maxLength={2}
          className={`${BASE} w-12 font-mono uppercase ${ISO2_RE.test(draft) ? tone : "border-red-500 bg-red-50"}`}
        />
      )}
    </div>
  );
}
