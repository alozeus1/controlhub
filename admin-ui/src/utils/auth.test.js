import { describe, it, expect, beforeEach } from "vitest";
import {
  setTokens, getToken, getRefreshToken, getCurrentUser, getCurrentRole,
  clearTokens, isAuthenticated,
} from "./auth";

describe("auth utils", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it("stores and restores tokens", () => {
    setTokens("acc", "ref");
    expect(getToken()).toBe("acc");
    expect(getRefreshToken()).toBe("ref");
  });

  it("restores the current user and role from storage", () => {
    sessionStorage.setItem("user", JSON.stringify({ email: "a@x.com", role: "admin" }));
    expect(getCurrentUser().email).toBe("a@x.com");
    expect(getCurrentRole()).toBe("admin");
  });

  it("returns null role safely when no user is stored", () => {
    expect(getCurrentUser()).toBeNull();
    expect(getCurrentRole()).toBeNull();
  });

  it("clears all tokens and user on logout", () => {
    setTokens("acc", "ref");
    sessionStorage.setItem("user", JSON.stringify({ role: "admin" }));
    localStorage.setItem("token", "legacy");
    clearTokens();
    expect(getToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(getCurrentUser()).toBeNull();
    expect(localStorage.getItem("token")).toBeNull();
  });

  it("isAuthenticated reflects token presence", () => {
    expect(isAuthenticated()).toBeFalsy();
    setTokens("acc");
    expect(isAuthenticated()).toBeTruthy();
  });
});
