import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { OcSelect } from "./OcSelect";

afterEach(cleanup);

const options = [
  { value: "", label: "全部公司" },
  { value: "bytedance", label: "字节跳动", count: 19302 },
  { value: "xiaomi", label: "小米", count: 4844, tone: "orange" as const },
];

describe("OcSelect", () => {
  it("shows the selected value and picks an option from the listbox", () => {
    const onChange = vi.fn();
    render(<OcSelect ariaLabel="公司" value="" options={options} onChange={onChange} />);
    const trigger = screen.getByRole("combobox", { name: "公司" });
    expect(trigger.textContent).toBe("全部公司");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("option", { name: "全部公司" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("option", { name: /^字节跳动/ }));

    expect(onChange).toHaveBeenCalledWith("bytedance");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("filters with search and chooses the highlighted option with Enter", () => {
    const onChange = vi.fn();
    render(<OcSelect ariaLabel="公司" value="" options={options} onChange={onChange} searchable />);
    fireEvent.click(screen.getByRole("combobox", { name: "公司" }));
    fireEvent.change(screen.getByRole("textbox", { name: "搜索公司" }), { target: { value: "小" } });

    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(["小米4,844"]);
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("xiaomi");
  });

  it("closes on Escape without changing the value or reaching the parent dialog", () => {
    const onChange = vi.fn();
    const parentKey = vi.fn();
    render(<div onKeyDown={parentKey}><OcSelect ariaLabel="公司" value="xiaomi" options={options} onChange={onChange} /></div>);
    const trigger = screen.getByRole("combobox", { name: "公司" });
    expect(trigger.querySelector('.oc-tag[data-tone="orange"]')?.textContent).toBe("小米");

    fireEvent.click(trigger);
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });

    expect(screen.queryByRole("listbox")).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
    expect(parentKey).not.toHaveBeenCalled();
  });
});
