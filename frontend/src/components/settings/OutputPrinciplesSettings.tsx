import { useEffect, useId, useState, type FormEvent } from "react";
import { Loader2, Save, ScrollText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { api } from "@/lib/api";

const fieldClass =
  "w-full rounded-md border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";

/**
 * Card for the operator's amendments to the agent's Output Principles. They
 * are stored outside the repository and added to the system prompt right
 * after the shipped principles, which stay untouched; blank text removes them.
 */
export function OutputPrinciplesSettings() {
  const { t } = useTranslation();
  const fieldId = useId();
  const [saved, setSaved] = useState("");
  const [draft, setDraft] = useState("");
  const [maxChars, setMaxChars] = useState(8000);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getOutputPrinciples()
      .then((settings) => {
        if (!alive) return;
        setSaved(settings.text);
        setDraft(settings.text);
        if (settings.max_chars > 0) setMaxChars(settings.max_chars);
      })
      .catch((loadError) => {
        if (alive) setError(loadError instanceof Error ? loadError.message : String(loadError));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const next = await api.updateOutputPrinciples(draft);
      setSaved(next.text);
      setDraft(next.text);
      toast.success(t("settings.outputPrinciples.saved"));
    } catch (saveError) {
      const message = saveError instanceof Error ? saveError.message : String(saveError);
      setError(message);
      toast.error(t("settings.outputPrinciples.saveFailed", { message }));
    } finally {
      setSaving(false);
    }
  };

  const tooLong = draft.trim().length > maxChars;
  const unchanged = draft.trim() === saved.trim();

  return (
    <form onSubmit={submit} className="rounded-lg border bg-card p-5 shadow-sm">
      <div className="mb-4 space-y-1">
        <div className="flex items-center gap-2">
          <ScrollText className="h-4 w-4 text-primary" />
          <h2 className="text-base font-semibold">{t("settings.outputPrinciples.title")}</h2>
        </div>
        <p className="text-sm text-muted-foreground">{t("settings.outputPrinciples.desc")}</p>
      </div>
      <label htmlFor={fieldId} className="sr-only">{t("settings.outputPrinciples.title")}</label>
      <textarea
        id={fieldId}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        disabled={loading || saving}
        rows={8}
        className={`${fieldClass} font-mono text-xs leading-relaxed`}
        placeholder={t("settings.outputPrinciples.placeholder")}
      />
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <span className={`text-xs ${tooLong ? "text-destructive" : "text-muted-foreground"}`}>
          {t("settings.outputPrinciples.count", { count: draft.trim().length, max: maxChars })}
        </span>
        {error && <span className="text-xs text-destructive">{error}</span>}
        <button
          type="submit"
          disabled={loading || saving || tooLong || unchanged}
          className="ms-auto inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-70"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {t("settings.outputPrinciples.save")}
        </button>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{t("settings.outputPrinciples.hint")}</p>
    </form>
  );
}
