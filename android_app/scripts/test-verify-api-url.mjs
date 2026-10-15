import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";

const cases = [
  { url: "http://api.example.com", smoke: "0", ok: false },
  { url: "https://localhost", smoke: "0", ok: false },
  { url: "https://192.168.1.99", smoke: "0", ok: false },
  { url: "https://android-build.invalid", smoke: "0", ok: false },
  { url: "https://android-build.invalid", smoke: "1", ok: true },
  { url: "https://api.example.com", smoke: "0", ok: true },
  { url: "https://api.example.com?key=secret", smoke: "0", ok: false },
  { url: "", smoke: "0", ok: false },
];
for (const test of cases) {
  const proc = spawnSync(process.execPath, ["scripts/verify-api-url.mjs"], {
    cwd: process.cwd(),
    encoding: "utf8",
    env: { ...process.env, ANDROID_API_URL: test.url, ANDROID_PLACEHOLDER: test.smoke },
  });
  assert.equal(proc.status === 0, test.ok, `unexpected URL check for ${test.url}`);
}
process.stdout.write("Validação dos domínios Android: 8 cenários aprovados.\n");
