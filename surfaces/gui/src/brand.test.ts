import { describe, expect, it } from "vitest";
import indexHtml from "../index.html?raw";
import rightRailSource from "./components/RightRail.tsx?raw";

describe("OpenCareer document brand", () => {
  it("uses OpenCareer in the browser title", () => {
    expect(indexHtml).toContain("<title>OpenCareer</title>");
    expect(indexHtml).not.toContain("<title>OpenWorker</title>");
  });

  it("uses OpenCareer in the primary workspace guidance", () => {
    expect(rightRailSource).toContain("OpenCareer 的规划");
    expect(rightRailSource).not.toContain("OpenWorker 的规划");
  });
});
