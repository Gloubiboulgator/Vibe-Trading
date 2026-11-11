import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import i18n from "@/i18n";
import { OutputPrinciplesSettings } from "@/components/settings/OutputPrinciplesSettings";

const apiMock = vi.hoisted(() => ({
  getOutputPrinciples: vi.fn(),
  updateOutputPrinciples: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: apiMock };
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() } }));

describe("OutputPrinciplesSettings", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    apiMock.getOutputPrinciples.mockReset();
    apiMock.updateOutputPrinciples.mockReset();
  });
  afterEach(() => cleanup());

  it("loads the saved amendments and saves an edit", async () => {
    apiMock.getOutputPrinciples.mockResolvedValue({ text: "Old rule.", max_chars: 8000 });
    apiMock.updateOutputPrinciples.mockResolvedValue({ text: "Give a clear verdict.", max_chars: 8000 });
    render(<OutputPrinciplesSettings />);

    const field = await screen.findByDisplayValue("Old rule.");
    const save = screen.getByRole("button", { name: "Save amendments" });
    expect(save).toBeDisabled();

    fireEvent.change(field, { target: { value: "Give a clear verdict." } });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => expect(apiMock.updateOutputPrinciples).toHaveBeenCalledWith("Give a clear verdict."));
    await waitFor(() => expect(save).toBeDisabled());
  });

  it("refuses text over the limit", async () => {
    apiMock.getOutputPrinciples.mockResolvedValue({ text: "", max_chars: 10 });
    render(<OutputPrinciplesSettings />);
    const field = await screen.findByRole("textbox");
    await waitFor(() => expect(field).toBeEnabled());

    fireEvent.change(field, { target: { value: "x".repeat(11) } });

    expect(screen.getByRole("button", { name: "Save amendments" })).toBeDisabled();
    expect(screen.getByText("11 / 10 characters")).toBeInTheDocument();
  });
});
