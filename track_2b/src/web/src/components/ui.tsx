// Small presentational primitives shared by all screens.
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { AlertTriangle, CheckCircle2, CircleHelp, Loader2, RotateCw, XCircle } from "lucide-react";
import { useI18n } from "../i18n";
import type { VerdictStatus } from "../types";

type Tone = "neutral" | "green" | "red" | "amber" | "dark";

const TONES: Record<Tone, string> = {
  neutral: "bg-neutral-100 text-neutral-700 ring-neutral-300",
  green: "bg-emerald-50 text-emerald-800 ring-emerald-300",
  red: "bg-red-50 text-red-800 ring-red-300",
  amber: "bg-amber-50 text-amber-900 ring-amber-300",
  dark: "bg-neutral-900 text-white ring-neutral-900",
};

export function Badge({
  tone = "neutral",
  icon,
  title,
  children,
}: {
  tone?: Tone;
  icon?: ReactNode;
  title?: string;
  children: ReactNode;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone]}`}
    >
      {icon}
      {children}
    </span>
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-neutral-900 text-white hover:bg-neutral-700 disabled:bg-neutral-400",
  secondary: "bg-white text-neutral-900 ring-1 ring-inset ring-neutral-300 hover:bg-neutral-50 disabled:text-neutral-400",
  ghost: "text-neutral-700 hover:bg-neutral-100 disabled:text-neutral-400",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  children,
  className = "",
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  loading?: boolean;
  icon?: ReactNode;
}) {
  const sizing = size === "sm" ? "px-2 py-1 text-xs" : "px-3 py-1.5 text-sm";
  return (
    <button
      type="button"
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center gap-1.5 rounded font-medium transition-colors disabled:cursor-not-allowed ${sizing} ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function Card({
  title,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-neutral-200 bg-white ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-200 px-4 py-2.5">
          {title && <h2 className="text-sm font-semibold text-neutral-900">{title}</h2>}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-neutral-600">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}
    </span>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="flex items-start gap-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900">
      <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="flex-1">
        <span className="font-semibold">{t("common.error")}: </span>
        {message}
      </div>
      {onRetry && (
        <Button size="sm" variant="ghost" onClick={onRetry} icon={<RotateCw className="h-3.5 w-3.5" aria-hidden />}>
          {t("common.retry")}
        </Button>
      )}
    </div>
  );
}

export function Notice({ tone = "amber", children }: { tone?: "amber" | "neutral"; children: ReactNode }) {
  const cls = tone === "amber" ? "border-amber-300 bg-amber-50 text-amber-900" : "border-neutral-200 bg-neutral-50 text-neutral-700";
  return (
    <div className={`flex items-start gap-2 rounded border px-3 py-2 text-sm ${cls}`}>
      {tone === "amber" && <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />}
      <div>{children}</div>
    </div>
  );
}

export function VerifiedBadge({ verified }: { verified: boolean }) {
  const { t } = useI18n();
  return verified ? (
    <Badge tone="green" icon={<CheckCircle2 className="h-3 w-3" aria-hidden />}>
      {t("common.verified")}
    </Badge>
  ) : (
    <Badge tone="amber" icon={<AlertTriangle className="h-3 w-3" aria-hidden />}>
      {t("common.unverified")}
    </Badge>
  );
}

/** Where an AI-produced text came from: a live Apertus call, the replay cache, or a template. */
export function SourceBadge({ source }: { source: "live" | "replay" | "template" | "none" }) {
  const { t } = useI18n();
  const tone: Tone = source === "live" ? "dark" : "neutral";
  return <Badge tone={tone}>{t(`src.${source}`)}</Badge>;
}

export const STATUS_TONE: Record<VerdictStatus, Tone> = { PASS: "green", FAIL: "red", UNSURE: "amber" };

export function StatusIcon({ status, className = "h-4 w-4" }: { status: VerdictStatus; className?: string }) {
  if (status === "PASS") return <CheckCircle2 className={className} aria-hidden />;
  if (status === "FAIL") return <XCircle className={className} aria-hidden />;
  return <CircleHelp className={className} aria-hidden />;
}

/** Tri-state check outcome (true / false / undecided) as an icon plus text label. */
export function CheckBadge({ passed, labels }: { passed: boolean | null; labels: [string, string, string] }) {
  const status: VerdictStatus = passed === true ? "PASS" : passed === false ? "FAIL" : "UNSURE";
  const label = passed === true ? labels[0] : passed === false ? labels[1] : labels[2];
  return (
    <Badge tone={STATUS_TONE[status]} icon={<StatusIcon status={status} className="h-3 w-3" />}>
      {label}
    </Badge>
  );
}
