import { buildCognitoAuthorizeUrl } from "./auth";

test("buildCognitoAuthorizeUrl returns null without config", () => {
  expect(buildCognitoAuthorizeUrl()).toBeNull();
});
