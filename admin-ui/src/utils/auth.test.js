describe("auth utils", () => {
  afterEach(() => {
    jest.resetModules();
    sessionStorage.clear();
    localStorage.clear();
    delete global.fetch;
    delete process.env.REACT_APP_AUTH_MODE;
  });

  test("buildCognitoAuthorizeUrl returns null without config", async () => {
    const { buildCognitoAuthorizeUrl } = await import("./auth");
    expect(buildCognitoAuthorizeUrl()).toBeNull();
  });

  test("tryRefreshToken uses refresh token in cognito mode when present", async () => {
    process.env.REACT_APP_AUTH_MODE = "cognito";
    sessionStorage.setItem("refresh_token", "refresh-123");

    global.fetch = jest.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ access_token: "new-access" }),
    });

    const { tryRefreshToken } = await import("./auth");
    const ok = await tryRefreshToken();

    expect(ok).toBe(true);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/auth\/refresh$/),
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ Authorization: "Bearer refresh-123" }),
      })
    );
    expect(sessionStorage.getItem("access_token")).toBe("new-access");
  });
});
