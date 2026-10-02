import { beforeEach, describe, expect, it, vi } from "vitest";
import { clewApi } from "../../../../src/scitex_clew/_django/static/clew_app/ts/api-client";
import { renderClaimsDag, renderProjectDag } from "../../../../src/scitex_clew/_django/static/clew_app/ts/clew-modes";

describe("Clew renders unavailable records and researcher text honestly", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows a store failure instead of an empty research history", async () => {
    vi.spyOn(clewApi, "getStats").mockResolvedValue({ success: false, error: "Private records are unavailable" });
    const area = document.createElement("div");
    await renderProjectDag(area, "alice/paper");
    expect(area.textContent).toContain("Private records are unavailable");
    expect(area.textContent).not.toContain("No Runs Yet");
  });

  it("shows a claim-store failure instead of claiming no claims exist", async () => {
    vi.spyOn(clewApi, "listClaims").mockResolvedValue({ success: false, error: "Claim records are unavailable" });
    vi.spyOn(clewApi, "getMermaidDag").mockResolvedValue({ success: false, error: "Unavailable" });
    const area = document.createElement("div");
    await renderClaimsDag(area);
    expect(area.textContent).toContain("Claim records are unavailable");
    expect(area.textContent).not.toContain("No Claims Registered");
  });

  it("preserves claim text as text rather than executable HTML", async () => {
    vi.spyOn(clewApi, "listClaims").mockResolvedValue({ success: true, data: { count: 1, claims: [{ claim_id: "claim", file_path: "<img src=x onerror=alert(1)>.tex", claim_type: "text", claim_value: "<script>bad()</script>", status: "registered" }] } } as any);
    vi.spyOn(clewApi, "getMermaidDag").mockResolvedValue({ success: true, data: { mermaid: "graph TD" } });
    const area = document.createElement("div");
    await renderClaimsDag(area);
    expect(area.querySelector(".claim-value")?.textContent).toContain("<script>bad()</script>");
    expect(area.querySelector("script")).toBeNull();
    expect(area.querySelector("img")).toBeNull();
  });
});
