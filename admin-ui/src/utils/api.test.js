import api from "./api";

jest.mock("./auth", () => ({
  getToken: () => "test-token",
  tryRefreshToken: jest.fn(async () => false),
  clearTokens: jest.fn(),
}));

describe("api utility", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("supports blob downloads", async () => {
    const blob = new Blob(["csv-data"], { type: "text/csv" });
    fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "text/csv", "content-disposition": "attachment; filename=test.csv" }),
      blob: async () => blob,
      text: async () => "csv-data",
    });

    const res = await api.get("/admin/people/export/csv", { responseType: "blob" });
    expect(res.data).toBe(blob);
    expect(res.headers["content-disposition"]).toContain("filename=test.csv");
  });

  test("parses JSON responses even when blob mode is requested", async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      status: 202,
      headers: new Headers({ "content-type": "application/json" }),
      blob: async () => new Blob(),
      text: async () => JSON.stringify({ code: "APPROVAL_REQUIRED", approval_request: { id: 7 } }),
    });

    const res = await api.get("/admin/people/export/csv", { responseType: "blob" });
    expect(res.data.code).toBe("APPROVAL_REQUIRED");
    expect(res.data.approval_request.id).toBe(7);
  });
});

