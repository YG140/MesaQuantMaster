// Verifique antes de empacotar: o APK só deve usar a API do próprio projeto.
import process from "node:process";

const endpoint = new URL(process.env.ANDROID_API_URL);
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 12_000);

try {
  const [root, health] = await Promise.all([
    fetch(new URL("/", endpoint), { signal: controller.signal }),
    fetch(new URL("/health", endpoint), { signal: controller.signal }),
  ]);
  if (!root.ok || !health.ok) throw Error(`API retornou HTTP ${root.status} / ${health.status}`);
  const rootPayload = await root.json();
  const healthPayload = await health.json();
  if (rootPayload.application !== "Mesa Quant Master" || healthPayload.status !== "healthy") {
    throw Error("o domínio informado não parece executar o backend Mesa Quant Master.");
  }
  process.stdout.write("API pública do Mesa Quant Master está acessível e respondeu corretamente.\n");
} catch (err) {
  process.stderr.write(`Falha ao validar o backend HTTPS: ${err instanceof Error ? err.message : String(err)}\n`);
  process.exitCode = 1;
} finally {
  clearTimeout(timeout);
}
