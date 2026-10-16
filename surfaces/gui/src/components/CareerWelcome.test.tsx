import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { CareerWelcome } from "./CareerWelcome";

afterEach(cleanup);

describe("CareerWelcome", () => {
  it("shows real Career tasks instead of developer suggestions", () => {
    render(
      <CareerWelcome
        onPrefill={vi.fn()}
        onImportResume={vi.fn()}
      />,
    );

    expect(screen.getByText("今天从哪里开始？")).toBeTruthy();
    expect(screen.getByText("建立求职档案")).toBeTruthy();
    expect(screen.getByText("发现合适岗位")).toBeTruthy();
    expect(screen.getByText("分析一份 JD")).toBeTruthy();
    expect(screen.queryByText("查看岗位雷达")).toBeNull();
    expect(screen.queryByText("查看求职档案")).toBeNull();
    expect(screen.queryByText("Run the test suite and summarize any failures.")).toBeNull();
  });

  it.each([
    ["发现合适岗位", "求职目标"],
    ["分析一份 JD", "JD"],
  ])("prefills the %s intent without sending it", (action, intent) => {
    const onPrefill = vi.fn();
    render(
      <CareerWelcome
        onPrefill={onPrefill}
        onImportResume={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: new RegExp(action) }));

    expect(onPrefill).toHaveBeenCalledOnce();
    expect(onPrefill).toHaveBeenCalledWith(expect.stringContaining(intent));
  });

  it("opens the dedicated resume importer without asking the model for a token", () => {
    const onImportResume = vi.fn();
    const onPrefill = vi.fn();
    render(
      <CareerWelcome
        onPrefill={onPrefill}
        onImportResume={onImportResume}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /建立求职档案/ }));

    expect(onImportResume).toHaveBeenCalledOnce();
    expect(onPrefill).not.toHaveBeenCalled();
  });

});
