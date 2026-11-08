import { useId, useState } from "react";
import { ChevronDown, Cpu, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { LLMProviderOption, LLMSettings, RunLLMSelection } from "@/lib/api";
import { effortLabelKey } from "@/lib/reasoningEffort";

interface Props {
  settings: LLMSettings | null;
  runtimeProvider?: string;
  runtimeModel?: string;
  runtimeReasoningEffort?: string;
  /** Per-run choice for the next messages; null means "use saved settings". */
  selection?: RunLLMSelection | null;
  /** Enables the picker. Omit to render the read-only bar. */
  onSelectionChange?: (selection: RunLLMSelection | null) => void;
  /** A run is streaming: show what it uses and lock the picker. */
  running?: boolean;
}

/** Providers a run may switch to: saved API key, plus the saved provider itself. */
export function runnableProviders(settings: LLMSettings): LLMProviderOption[] {
  return settings.providers.filter(
    (item) => item.name === settings.provider || item.api_key_configured,
  );
}

/** The saved settings expressed as a selection. */
export function savedSelection(settings: LLMSettings): RunLLMSelection {
  return {
    provider: settings.provider,
    model: settings.model_name,
    reasoning_effort: settings.reasoning_effort,
  };
}

/** Normalize a choice: identical to saved settings means no override (null). */
export function normalizeSelection(
  settings: LLMSettings,
  next: RunLLMSelection,
): RunLLMSelection | null {
  const saved = savedSelection(settings);
  const same = next.provider === saved.provider
    && next.model.trim() === saved.model
    && next.reasoning_effort === saved.reasoning_effort;
  return same ? null : { ...next, model: next.model.trim() };
}

export function ModelRuntimeBar({
  settings,
  runtimeProvider,
  runtimeModel,
  runtimeReasoningEffort,
  selection = null,
  onSelectionChange,
  running = false,
}: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  if (!settings) return null;

  const pickerEnabled = Boolean(onSelectionChange);
  // The read-only bar shows what the run reported. With the picker, a run
  // that streams shows what it reports, and an idle bar shows what the next
  // message will use (the per-run choice, else saved settings): showing the
  // last run's model made a session whose last run used another provider
  // look as if the saved settings had changed.
  const showRuntime = running || !pickerEnabled;
  const next = selection ?? savedSelection(settings);
  const providerId = (showRuntime ? runtimeProvider : undefined) || next.provider;
  const provider = settings.providers.find((item) => item.name === providerId);
  const providerLabel = provider?.label || providerId || t("agent.unknownProvider");
  const model = (showRuntime ? runtimeModel : undefined) || next.model || t("agent.unknownModel");
  const reasoningEffort = showRuntime && runtimeReasoningEffort !== undefined
    ? runtimeReasoningEffort
    : next.reasoning_effort;
  const effortKey = effortLabelKey(reasoningEffort);
  const effortLabel = effortKey ? t(effortKey) : t("settings.providerDefault");

  const current = selection ?? savedSelection(settings);
  const currentProvider = settings.providers.find((item) => item.name === current.provider);
  const providers = runnableProviders(settings);
  const modelSuggestions = Array.from(new Set([
    ...(current.provider === settings.provider ? [settings.model_name] : []),
    currentProvider?.default_model ?? "",
    ...(currentProvider?.model_options ?? []),
  ].filter(Boolean)));

  const update = (next: RunLLMSelection) => onSelectionChange?.(normalizeSelection(settings, next));
  const changeProvider = (name: string) => {
    if (name === settings.provider) {
      update(savedSelection(settings));
      return;
    }
    const target = settings.providers.find((item) => item.name === name);
    update({ provider: name, model: target?.default_model ?? "", reasoning_effort: "" });
  };

  const summary = (
    <>
      <span className="relative flex h-2 w-2 shrink-0" aria-hidden="true">
        <span className="absolute inline-flex h-full w-full rounded-full bg-success/30" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
      </span>
      <span className="shrink-0 font-medium text-foreground">{providerLabel}</span>
      <span className="text-muted-foreground/60">·</span>
      <span className="truncate font-mono text-[11px] text-muted-foreground" title={model}>{model}</span>
      {pickerEnabled && selection && (
        <span className="shrink-0 rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
          {t("agent.runPicker.custom")}
        </span>
      )}
    </>
  );

  return (
    <div className="shrink-0 border-b border-border/70 bg-background/95 px-6 py-2 backdrop-blur-sm">
      <div className="mx-auto flex max-w-3xl items-center gap-2 overflow-hidden text-xs">
        {pickerEnabled ? (
          <button
            type="button"
            className="flex min-w-0 items-center gap-2 rounded-md px-1 py-0.5 hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-70"
            aria-expanded={open}
            aria-controls={panelId}
            title={t("agent.runPicker.change")}
            disabled={running}
            onClick={() => setOpen((value) => !value)}
          >
            {summary}
            <ChevronDown className={`h-3 w-3 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
          </button>
        ) : summary}
        <span className="ml-auto inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border/70 bg-muted/35 px-2 py-0.5 text-[10px] text-muted-foreground">
          <Cpu className="h-3 w-3" aria-hidden="true" />
          {t("agent.reasoningStrength")}: {effortLabel}
        </span>
      </div>
      {pickerEnabled && open && !running && (
        <div
          id={panelId}
          role="group"
          aria-label={t("agent.runPicker.title")}
          className="mx-auto mt-2 max-w-3xl rounded-lg border border-border/70 bg-card p-3 text-xs shadow-sm"
          onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}
        >
          <div className="mb-2 font-medium text-foreground">{t("agent.runPicker.title")}</div>
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground">{t("agent.runPicker.provider")}</span>
              <select
                className="rounded-md border border-border bg-background px-2 py-1.5"
                value={current.provider}
                onChange={(event) => changeProvider(event.target.value)}
              >
                {providers.map((item) => (
                  <option key={item.name} value={item.name}>{item.label}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground">{t("agent.runPicker.model")}</span>
              <input
                className="rounded-md border border-border bg-background px-2 py-1.5 font-mono"
                list={`${panelId}-models`}
                value={current.model}
                spellCheck={false}
                onChange={(event) => update({ ...current, model: event.target.value })}
              />
              <datalist id={`${panelId}-models`}>
                {modelSuggestions.map((item) => <option key={item} value={item} />)}
              </datalist>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground">{t("agent.runPicker.effort")}</span>
              <select
                className="rounded-md border border-border bg-background px-2 py-1.5"
                value={current.reasoning_effort}
                onChange={(event) => update({ ...current, reasoning_effort: event.target.value })}
              >
                <option value="">{t("settings.providerDefault")}</option>
                {(currentProvider?.reasoning_efforts ?? []).map((level) => {
                  const key = effortLabelKey(level);
                  return <option key={level} value={level}>{key ? t(key) : level}</option>;
                })}
              </select>
            </label>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-muted-foreground">
            <span>{t("agent.runPicker.hint")}</span>
            {selection && (
              <button
                type="button"
                className="ms-auto inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 hover:bg-muted/50"
                onClick={() => onSelectionChange?.(null)}
              >
                <RotateCcw className="h-3 w-3" aria-hidden="true" />
                {t("agent.runPicker.reset")}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
