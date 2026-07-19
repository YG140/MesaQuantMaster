import { spawn } from "node:child_process";
import process from "node:process";

const isWindows = process.platform === "win32";
const viteBin = isWindows ? "node_modules\\.bin\\vite.cmd" : "node_modules/.bin/vite";
const playwrightBin = isWindows
  ? "node_modules\\.bin\\playwright.cmd"
  : "node_modules/.bin/playwright";
const host = "127.0.0.1";
const port = "5173";
const url = `http://${host}:${port}`;

let server;

async function main() {
  await assertPortFree();
  server = spawnCommand(viteBin, ["--host", host, "--port", port, "--strictPort"], {
    cwd: process.cwd(),
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
    env: {
      ...process.env,
      VITE_API_BASE_URL: url,
    },
  });

  server.stdout.on("data", (chunk) => process.stdout.write(chunk));
  server.stderr.on("data", (chunk) => process.stderr.write(chunk));

  await waitForServer();
  const result = await runPlaywright();
  process.exitCode = result;
}

async function assertPortFree() {
  try {
    await fetch(url, { signal: AbortSignal.timeout(700) });
  } catch {
    return;
  }
  throw new Error(`Porta ${port} ja esta em uso. Encerre o processo antes do E2E.`);
}

async function waitForServer() {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`Vite encerrou antes de responder em ${url}.`);
    }
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) {
        return;
      }
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  throw new Error(`Vite nao respondeu em ${url}.`);
}

function runPlaywright() {
  return new Promise((resolve) => {
    const child = spawnCommand(playwrightBin, ["test"], {
      cwd: process.cwd(),
      stdio: "inherit",
      windowsHide: true,
      env: {
        ...process.env,
        PLAYWRIGHT_BASE_URL: url,
        VITE_API_BASE_URL: url,
      },
    });
    child.on("close", (code) => resolve(code ?? 1));
  });
}

function spawnCommand(command, args, options) {
  if (!isWindows) {
    return spawn(command, args, options);
  }
  return spawn("cmd.exe", ["/d", "/s", "/c", command, ...args], options);
}

async function stopServer() {
  if (!server || server.exitCode !== null) {
    return;
  }
  if (isWindows) {
    await new Promise((resolve) => {
      const killer = spawn("taskkill", ["/pid", String(server.pid), "/T", "/F"], {
        stdio: "ignore",
        windowsHide: true,
      });
      killer.on("close", resolve);
      killer.on("error", resolve);
    });
  } else {
    server.kill("SIGTERM");
  }
}

try {
  await main();
} finally {
  await stopServer();
  process.exit(process.exitCode ?? 0);
}
