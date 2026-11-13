import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ModelRuntimeBar, normalizeSelection } from "../ModelRuntimeBar";
import type { LLMSettings } from "@/lib/api";

const settings: LLMSettings = {
  provider: "deepseek",
  model_name: "deepseek-v4-flash",
  base_url: "https://api.deepseek.com",
  api_key_configured: true,
  api_key_required: true,
  temperature: 0,
  timeout_seconds: 120,
  max_retries: 2,
  reasoning_effort: "high",
  sse_timeout_seconds: 90,
  env_path: "agent/.env",
  providers: [{
    name: "deepseek",
    label: "DeepSeek",
    base_url_env: "LANGCHAIN_BASE_URL",
    default_model: "deepseek-chat",
    default_base_url: "https://api.deepseek.com",
    api_key_required: true,
  }],
};

const usage = {
  input_tokens: 1_200_000, output_tokens: 34_000, cache_read_tokens: 800_000,
  cache_creation_tokens: 300_000, total_tokens: 1_234_000, cost_usd: 4.2, runs: 3, unpriced_runs: 0,
};

describe("ModelRuntimeBar", () => {
  it("shows the conversation's cost and tokens, with the breakdown on hover", () => {
    render(<ModelRuntimeBar settings={settings} usage={usage} />);

    const chip = screen.getByText("$4.20 · 1.2M tokens");
    expect(chip.parentElement).toHaveAttribute("title", expect.stringContaining("over 3 answers"));
  });

  it("shows tokens alone for a model without a known price, and nothing before any run", () => {
    const { rerender } = render(
      <ModelRuntimeBar settings={settings} usage={{ ...usage, cost_usd: null, unpriced_runs: 3 }} />,
    );
    expect(screen.getByText("1.2M tokens")).toBeInTheDocument();
    expect(screen.getByText("1.2M tokens").parentElement)
      .toHaveAttribute("title", expect.stringContaining("not in the cost: 3"));

    rerender(<ModelRuntimeBar settings={settings} usage={{ ...usage, total_tokens: 0 }} />);
    expect(screen.queryByText(/tokens/)).not.toBeInTheDocument();
  });

  it("shows provider, provider-reported model and configured reasoning effort", () => {
    render(
      <ModelRuntimeBar
        settings={settings}
        runtimeProvider="deepseek"
        runtimeModel="deepseek-v4-flash-202607"
      />,
    );

    expect(screen.getByText("DeepSeek")).toBeInTheDocument();
    expect(screen.getByText("deepseek-v4-flash-202607")).toBeInTheDocument();
    expect(screen.getByText(/Reasoning Effort: High/)).toBeInTheDocument();
  });

  it("distinguishes explicit no-reasoning from the provider default", () => {
    render(
      <ModelRuntimeBar
        settings={{ ...settings, reasoning_effort: "none" }}
      />,
    );

    expect(screen.getByText(/Reasoning Effort: None \(explicit\)/)).toBeInTheDocument();
  });

  it("labels the claude-cli xhigh level instead of falling back to the default", () => {
    render(
      <ModelRuntimeBar
        settings={settings}
        runtimeProvider="claude-cli"
        runtimeModel="claude-opus-5-5"
        runtimeReasoningEffort="xhigh"
      />,
    );

    expect(screen.getByText(/Reasoning Effort: Extra high/)).toBeInTheDocument();
  });

  it("shows the persisted historical reasoning effort instead of current settings", () => {
    render(
      <ModelRuntimeBar
        settings={{ ...settings, reasoning_effort: "low" }}
        runtimeProvider="deepseek"
        runtimeModel="deepseek-v4-flash-202607"
        runtimeReasoningEffort="high"
      />,
    );

    expect(screen.getByText(/Reasoning Effort: High/)).toBeInTheDocument();
    expect(screen.queryByText(/Reasoning Effort: Low/)).not.toBeInTheDocument();
  });

  describe("per-run picker", () => {
    const multi: LLMSettings = {
      ...settings,
      provider: "openrouter",
      model_name: "deepseek/deepseek-v4-pro",
      reasoning_effort: "",
      providers: [
        { name: "openrouter", label: "OpenRouter", base_url_env: "OPENROUTER_BASE_URL", default_model: "deepseek/deepseek-v4-pro",
          default_base_url: "https://openrouter.ai/api/v1", api_key_required: true, api_key_configured: true, reasoning_efforts: ["low", "high"] },
        { name: "anthropic", label: "Anthropic", base_url_env: "ANTHROPIC_BASE_URL", default_model: "claude-sonnet-4-6",
          default_base_url: "https://api.anthropic.com", api_key_required: true, api_key_configured: true, reasoning_efforts: ["low", "high", "max"] },
        { name: "openai", label: "OpenAI", base_url_env: "OPENAI_BASE_URL", default_model: "gpt-5.5",
          default_base_url: "https://api.openai.com/v1", api_key_required: true, api_key_configured: false },
      ],
    };

    it("offers only providers with a saved key and switches to the provider default model", () => {
      const onChange = vi.fn();
      render(<ModelRuntimeBar settings={multi} selection={null} onSelectionChange={onChange} />);
      fireEvent.click(screen.getByRole("button", { name: /OpenRouter/ }));

      const providerSelect = screen.getByLabelText("Provider");
      expect([...(providerSelect as HTMLSelectElement).options].map((o) => o.value)).toEqual(["openrouter", "anthropic"]);
      fireEvent.change(providerSelect, { target: { value: "anthropic" } });
      expect(onChange).toHaveBeenLastCalledWith({ provider: "anthropic", model: "claude-sonnet-4-6", reasoning_effort: "" });
    });

    it("shows the chosen run model with a Custom badge and resets to saved settings", () => {
      const onChange = vi.fn();
      render(
        <ModelRuntimeBar
          settings={multi}
          runtimeProvider="openrouter"
          runtimeModel="deepseek/deepseek-v4-pro"
          selection={{ provider: "anthropic", model: "claude-sonnet-5-5", reasoning_effort: "high" }}
          onSelectionChange={onChange}
        />,
      );
      expect(screen.getByText("claude-sonnet-5-5")).toBeInTheDocument();
      expect(screen.getByText("Custom")).toBeInTheDocument();
      expect(screen.getByText(/Reasoning Effort: High/)).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /Anthropic/ }));
      fireEvent.click(screen.getByRole("button", { name: /Use saved settings/ }));
      expect(onChange).toHaveBeenLastCalledWith(null);
    });

    it("treats a choice equal to saved settings as no override", () => {
      expect(normalizeSelection(multi, { provider: "openrouter", model: " deepseek/deepseek-v4-pro ", reasoning_effort: "" })).toBeNull();
    });

    it("shows the saved settings, not the last run's provider, when idle", () => {
      // The last run of the session used Anthropic through the picker; the next
      // message will use the saved OpenRouter settings, so the bar says so.
      render(
        <ModelRuntimeBar
          settings={multi}
          runtimeProvider="anthropic"
          runtimeModel="claude-sonnet-5-5"
          runtimeReasoningEffort="high"
          selection={null}
          onSelectionChange={vi.fn()}
        />,
      );
      expect(screen.getByText("OpenRouter")).toBeInTheDocument();
      expect(screen.getByText("deepseek/deepseek-v4-pro")).toBeInTheDocument();
      expect(screen.queryByText("claude-sonnet-5-5")).not.toBeInTheDocument();
      expect(screen.getByText(/Reasoning Effort: Provider default/)).toBeInTheDocument();
    });

    it("shows what the streaming run reports", () => {
      render(
        <ModelRuntimeBar
          settings={multi}
          runtimeProvider="anthropic"
          runtimeModel="claude-sonnet-5-5"
          selection={null}
          onSelectionChange={vi.fn()}
          running
        />,
      );
      expect(screen.getByText("claude-sonnet-5-5")).toBeInTheDocument();
    });

    it("offers the provider's live models once the picker opens", async () => {
      const loadModels = vi.fn().mockResolvedValue(["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"]);
      render(
        <ModelRuntimeBar settings={multi} selection={null} onSelectionChange={vi.fn()} loadModels={loadModels} />,
      );
      expect(loadModels).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: /OpenRouter/ }));
      expect(loadModels).toHaveBeenCalledWith("openrouter");
      await waitFor(() => expect(loadModels).toHaveBeenCalledTimes(1));
      // The field already holds the saved model; every model is still offered
      // (a datalist filtered on that text and showed none, 2026-11-11).
      fireEvent.click(screen.getByRole("combobox", { name: "Model" }));
      expect(await screen.findByRole("option", { name: /deepseek-v4-flash/ })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /deepseek-v4-pro/ })).toBeInTheDocument();
    });

    it("locks the picker while a run is streaming", () => {
      render(<ModelRuntimeBar settings={multi} selection={null} onSelectionChange={vi.fn()} running />);
      expect(screen.getByRole("button", { name: /OpenRouter/ })).toBeDisabled();
    });
  });
});
