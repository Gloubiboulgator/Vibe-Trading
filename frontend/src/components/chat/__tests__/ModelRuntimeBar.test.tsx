import { fireEvent, render, screen } from "@testing-library/react";
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

describe("ModelRuntimeBar", () => {
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

    it("locks the picker while a run is streaming", () => {
      render(<ModelRuntimeBar settings={multi} selection={null} onSelectionChange={vi.fn()} running />);
      expect(screen.getByRole("button", { name: /OpenRouter/ })).toBeDisabled();
    });
  });
});
