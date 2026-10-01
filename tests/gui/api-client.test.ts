import { beforeEach, describe, expect, it, vi } from "vitest";
import { ClewApiClient } from "../../src/scitex_clew/_django/static/clew_app/ts/api-client";

describe("Clew requests stay with the project shown in this tab", () => {
  beforeEach(() => {
    document.head.innerHTML = '<meta name="stx-mount" content="/apps/clew">';
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/apps/clew/");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      json: async () => ({ success: true, data: {} }),
    }));
  });

  it("sends the rendered project for data and write requests", async () => {
    document.body.innerHTML = '<div id="workspace-project-config" data-username="alice" data-project-slug="paper"></div>';
    const api = new ClewApiClient();
    await api.getStats();
    await api.addExamples();
    for (const call of vi.mocked(fetch).mock.calls) {
      expect(new URL(String(call[0])).searchParams.get("project")).toBe("alice/paper");
    }
  });

  it("keeps the rendered project when the URL names an older choice", async () => {
    window.history.replaceState({}, "", "/apps/clew/?project=alice/old");
    document.body.innerHTML = '<div id="workspace-project-config" data-username="alice" data-project-slug="paper"></div>';
    await new ClewApiClient().listRuns({ limit: 10, offset: 5 });
    const url = new URL(String(vi.mocked(fetch).mock.calls[0][0]));
    expect(url.searchParams.get("project")).toBe("alice/paper");
    expect(url.searchParams.get("offset")).toBe("5");
  });

  it("retains explicit inaccessible choices for the server to reject", async () => {
    window.history.replaceState({}, "", "/apps/clew/?project=bob/private");
    await new ClewApiClient().getStats();
    expect(new URL(String(vi.mocked(fetch).mock.calls[0][0])).searchParams.get("project")).toBe("bob/private");
  });

  it("surfaces unavailable stores instead of inventing empty statistics", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      json: async () => ({ success: false, error: "Private Clew store is unavailable" }),
    } as Response);
    const response = await new ClewApiClient().getStats();
    expect(response.success).toBe(false);
    expect(response.data).toBeUndefined();
    expect(response.error).toContain("unavailable");
  });

  it("uses the same API client at the standalone root", async () => {
    document.head.innerHTML = '<meta name="stx-mount" content="">';
    document.body.innerHTML = '<div id="workspace-project-config" data-project-ref="paper"></div>';
    window.history.replaceState({}, "", "/?project=paper");
    await new ClewApiClient().getStats();
    const url = new URL(String(vi.mocked(fetch).mock.calls[0][0]));
    expect(url.pathname).toBe("/api/stats/");
    expect(url.searchParams.get("project")).toBe("paper");
  });

  it("honors a custom plugin mount and keeps file previews scoped", () => {
    document.body.innerHTML = '<div data-clew-config data-mount="/custom/clew"></div><div id="workspace-project-config" data-project-ref="alice/paper"></div>';
    const url = new URL(new ClewApiClient().fileContentUrl("figure.png", true));
    expect(url.pathname).toBe("/custom/clew/api/file/");
    expect(url.searchParams.get("project")).toBe("alice/paper");
    expect(url.searchParams.get("raw")).toBe("true");
  });

  it("fails without a mount marker instead of guessing a host API", async () => {
    document.head.innerHTML = "";
    const response = await new ClewApiClient().getStats();
    expect(response.success).toBe(false);
    expect(response.error).toContain("mount configuration is missing");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("refuses protocol-relative mounts", async () => {
    document.head.innerHTML = '<meta name="stx-mount" content="//another-host">';
    const response = await new ClewApiClient().getStats();
    expect(response.success).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
  });
});
