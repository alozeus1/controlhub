import { parseHashToken } from "./AuthCallback";

test("parseHashToken extracts id_token", () => {
  const token = parseHashToken("#id_token=abc123&access_token=def");
  expect(token).toBe("abc123");
});
