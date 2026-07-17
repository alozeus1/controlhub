import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import api from "./api";

vi.mock("./auth", () => ({
  getToken: () => "test-token",
  tryRefreshToken: vi.fn(async () => false),
  clearTokens: vi.fn(),
}));

describe("api client", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });
  afterEach(() => {
    vi.resetAllMocks();
  });

  it("attaches the Authorization header", async () => {
    fetch.mockResolvedValueOnce({
      ok: true, status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      text: async () => JSON.stringify({ ok: true }),
    });
    await api.get("/admin/thing");
    const [, opts] = fetch.mock.calls[0];
    expect(opts.headers.Authorization).toBe("Bearer test-token");
  });

  it("supports blob downloads", async () => {
    const blob = new Blob(["csv-data"], { type: "text/csv" });
    fetch.mockResolvedValueOnce({
      ok: true, status: 200,
      headers: new Headers({ "content-type": "text/csv", "content-disposition": "attachment; filename=test.csv" }),
      blob: async () => blob,
      text: async () => "csv-data",
    });
    const res = await api.get("/admin/people/export/csv", { responseType: "blob" });
    expect(res.data).toBe(blob);
    expect(res.headers["content-disposition"]).toContain("filename=test.csv");
  });

  it("parses JSON even when blob mode is requested", async () => {
    fetch.mockResolvedValueOnce({
      ok: true, status: 202,
      headers: new Headers({ "content-type": "application/json" }),
      blob: async () => new Blob(),
      text: async () => JSON.stringify({ code: "APPROVAL_REQUIRED", approval_request: { id: 7 } }),
    });
    const res = await api.get("/admin/people/export/csv", { responseType: "blob" });
    expect(res.data.code).toBe("APPROVAL_REQUIRED");
  });

  it("throws a structured error on 4xx and surfaces the backend message", async () => {
    fetch.mockResolvedValueOnce({
      ok: false, status: 403,
      headers: new Headers({ "content-type": "application/json" }),
      text: async () => JSON.stringify({ error: "Forbidden", code: "FORBIDDEN" }),
    });
    await expect(api.get("/admin/secret")).rejects.toMatchObject({
      message: expect.stringContaining("Forbidden"),
      response: { status: 403 },
    });
  });

  it("does not redirect on 401 when skip401Redirect is set (login flow)", async () => {
    fetch.mockResolvedValueOnce({
      ok: false, status: 401,
      headers: new Headers({ "content-type": "application/json" }),
      text: async () => JSON.stringify({ error: "Invalid email or password" }),
    });
    await expect(
      api.post("/auth/login", { email: "x", password: "y" }, { skip401Redirect: true })
    ).rejects.toMatchObject({ response: { status: 401 } });
  });
});
