// Fail closed: a native build cannot silently use localhost or HTTP.
import process from "node:process";

const sample = "https://android-build.invalid";
const raw = (process.env.ANDROID_API_URL ?? "").trim();
const smoke = process.env.ANDROID_PLACEHOLDER === "1";

function fail(message) {
  process.stderr.write(`Configuração Android inválida: ${message}\n`);
  process.exit(1);
}
if (!raw) fail("informe a URL pública HTTPS da API. Configure a variável MESA_API_BASE_URL ou o input api_base_url do workflow.");
if (raw === sample && !smoke) fail("URL fictícia permitida apenas na verificação de compilação da PR.");
let address;
try { address = new URL(raw); } catch { fail("URL malformada."); }
if (address.protocol !== "https:") fail("a API precisa de HTTPS.");
if (address.username || address.password || address.search || address.hash) fail("a URL não deve conter credenciais, parâmetros nem fragmentos.");
if (address.pathname !== "/") fail("a URL deve apontar para a raiz da API, sem caminho adicional.");
if (address.port && address.port !== "443") fail("use a porta HTTPS padrão (443).");
const host = address.hostname.toLowerCase();
if (!host.includes(".") || /^(localhost|127\.|0\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host) || host.endsWith(".local")) {
  fail("a API precisa ter um domínio público; localhost e IP privado não funcionam sem o computador.");
}
if (!smoke && (host.endsWith(".invalid") || host.endsWith(".test") || host.endsWith(".example") || host === "example.com")) {
  fail("endereço fictício não é permitido para gerar um APK instalável.");
}
if (smoke && raw !== sample) fail("o teste da PR deve usar somente a URL fictícia pré-definida.");
process.stdout.write(`API Android verificada: ${address.origin} (${smoke ? "compilação sem backend" : "produção de teste"})\n`);
