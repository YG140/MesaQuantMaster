// Verifique antes de empacotar: o APK só deve usar a API do próprio projeto.
import process from "node:process";

const endpoint = new URL(process.env.ANDROID_API_URL);
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 12_000);

try {
  const [root, health, ready] = await Promise.all([
    fetch(new URL("/", endpoint), { signal: controller.signal }),
    fetch(new URL("/health", endpoint), { signal: controller.signal }),
    fetch(new URL("/ready", endpoint), { signal: controller.signal }),
  ]);
  if (!root.ok || !health.ok || !ready.ok) throw Error(`API/banco não prontos: HTTP ${root.status}/${health.status}/${ready.status}`);
  const rootPayload = await root.json();
  const healthPayload = await health.json();
  const readyPayload = await ready.json();
  if (rootPayload.application !== "Mesa Quant Master" || healthPayload.status !== "healthy" || readyPayload.status !== "ready") {
    throw Error("o domínio informado não parece executar um backend Mesa Quant Master com banco pronto.");
  }
  process.stdout.write("API pública e banco PostgreSQL estão acessíveis para o APK.\n");
} catch (err) {
  process.stderr.write(`Falha ao validar o backend HTTPS: ${err instanceof Error ? err.message : String(err)}\n`);
  process.exitCode = 1;
} finally {
  clearTimeout(timeout);
}
