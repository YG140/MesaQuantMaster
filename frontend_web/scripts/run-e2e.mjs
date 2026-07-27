import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { resolve } from "node:path";
import process from "node:process";

const host = "127.0.0.1";
const port = 5173;
const frontendUrl = `http://${host}:${port}`;
const mockedApiUrl = "http://127.0.0.1:8000";
const viteEntry = resolve("node_modules/vite/bin/vite.js");
const playwrightEntry = resolve("node_modules/@playwright/test/cli.js");
let vite;

function log(message) {
  process.stdout.write(`[e2e] ${message}\n`);
}

async function assertPortFree() {
  await new Promise((resolvePromise, reject) => {
    const probe = createServer();
    probe.once("error", () => reject(new Error(`Porta ${port} já está em uso.`)));
    probe.listen(port, host, () => probe.close(resolvePromise));
  });
}

function spawnNode(entry, args, stdio) {
  return spawn(process.execPath, [entry, ...args], {
    cwd: process.cwd(),
    stdio,
    windowsHide: true,
    env: {
      ...process.env,
      APP_ENV: "test",
      DATABASE_URL: "sqlite:///./.pytest_cache/test_playwright.db",
      VITE_API_BASE_URL: mockedApiUrl,
      PLAYWRIGHT_BASE_URL: frontendUrl,
    },
  });
}

async function waitForVite() {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (vite.exitCode !== null) {
      throw new Error(`Vite encerrou prematuramente com código ${vite.exitCode}.`);
    }
    try {
      const response = await fetch(frontendUrl, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) return;
    } catch {
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 300));
    }
  }
  throw new Error(`Vite não ficou pronto em ${frontendUrl}.`);
}

async function stopTree(child) {
  if (!child || child.exitCode !== null) return;
  child.kill("SIGTERM");
  const exited = await Promise.race([
    new Promise((resolvePromise) => child.once("close", () => resolvePromise(true))),
    new Promise((resolvePromise) => setTimeout(() => resolvePromise(false), 3_000)),
  ]);
  if (!exited && process.platform === "win32") {
    const killer = spawn("taskkill.exe", ["/pid", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
    await Promise.race([
      new Promise((resolvePromise) => {
        killer.once("close", resolvePromise);
        killer.once("error", resolvePromise);
      }),
      new Promise((resolvePromise) => setTimeout(resolvePromise, 5_000)),
    ]);
  }
}

try {
  log("verificando porta 5173");
  await assertPortFree();
  log("iniciando Vite; backend real não será iniciado");
  vite = spawnNode(viteEntry, ["--host", host, "--port", String(port), "--strictPort"], [
    "ignore", "pipe", "pipe",
  ]);
  vite.stdout.pipe(process.stdout);
  vite.stderr.pipe(process.stderr);
  await waitForVite();
  log("Vite pronto; iniciando Playwright com API interceptada por mocks");
  const playwright = spawnNode(playwrightEntry, ["test", "--reporter=line"], "inherit");
  const exitCode = await new Promise((resolvePromise, reject) => {
    playwright.once("error", reject);
    playwright.once("close", (code) => resolvePromise(code ?? 1));
  });
  process.exitCode = exitCode;
} catch (error) {
  process.stderr.write(`[e2e] ${error instanceof Error ? error.stack : error}\n`);
  process.exitCode = 1;
} finally {
  log("encerrando árvore de processos do Vite");
  await stopTree(vite);
}
