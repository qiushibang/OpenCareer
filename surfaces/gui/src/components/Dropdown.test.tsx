import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";

import { Dropdown } from "./Dropdown";

afterEach(cleanup);

function Harness({ onConfigure }: { onConfigure: () => void }) {
  const [model, setModel] = useState("deepseek:deepseek-v4-flash");
  return (
    <Dropdown
      value={model}
      options={[
        { value: "deepseek:deepseek-v4-flash", label: "DeepSeek V4 Flash" },
        { value: "kimi:kimi-latest", label: "Kimi" },
      ]}
      onChange={setModel}
      footer={
        <button data-testid="configure-models" onClick={onConfigure}>
          ⚙ 配置自定义模型
        </button>
      }
    />
  );
}

describe("Dropdown footer", () => {
  it("renders the footer action and closes the menu on click without changing the model", () => {
    const onConfigure = vi.fn();
    render(<Harness onConfigure={onConfigure} />);

    fireEvent.click(screen.getByText("DeepSeek V4 Flash"));
    expect(screen.getByTestId("configure-models")).toBeTruthy();

    fireEvent.click(screen.getByTestId("configure-models"));
    expect(onConfigure).toHaveBeenCalledOnce();
    // Menu closed (footer no longer in the document) and the value unchanged.
    expect(screen.queryByTestId("configure-models")).toBeNull();
    expect(screen.getByText("DeepSeek V4 Flash")).toBeTruthy();
  });

  it("still selects options normally when a footer is present", () => {
    const onConfigure = vi.fn();
    render(<Harness onConfigure={onConfigure} />);

    fireEvent.click(screen.getByText("DeepSeek V4 Flash"));
    fireEvent.click(screen.getByText("Kimi"));
    expect(onConfigure).not.toHaveBeenCalled();
  });
});
