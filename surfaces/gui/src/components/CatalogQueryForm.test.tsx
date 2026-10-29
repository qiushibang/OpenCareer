import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CatalogQueryForm } from "./CatalogQueryForm";

vi.mock("../api", () => ({ careerCatalogRequest: async () => ({ companies: [{ slug: "bytedance", name: "字节跳动" }], job_families: { product: "产品" }, directions: { evaluation_product: "评测产品" } }) }));

describe("catalog query form", () => {
  it("combines city and job function without silently turning search into subscription", async () => {
    const submit = vi.fn();
    render(<CatalogQueryForm onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText("工作城市"), { target: { value: "北京" } });
    fireEvent.change(await screen.findByLabelText("岗位职能"), { target: { value: "product" } });
    fireEvent.click(screen.getByRole("button", { name: "应用筛选" }));
    expect(submit.mock.calls[0][0].condition.all).toEqual(expect.arrayContaining([
      { field: "locations", op: "in", values: ["北京"] },
      { field: "job_family", op: "in", values: ["product"] },
    ]));
    expect(submit.mock.calls[0][0].today).toBe(false);
  });
});
