// Capacitor gera o código Android em CI. Reforce segurança do WebView
// antes do Gradle: sem HTTP puro e sem backup automático de dados locais.
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const filename = resolve("android/app/src/main/AndroidManifest.xml");
let xml = readFileSync(filename, "utf8");
if (!xml.includes("<application")) throw Error("AndroidManifest sem elemento application");

for (const [key, value] of [["usesCleartextTraffic", "false"], ["allowBackup", "false"]]) {
  const regexp = new RegExp(`android:${key}="[^"]*"`);
  if (regexp.test(xml)) xml = xml.replace(regexp, `android:${key}="${value}"`);
  else xml = xml.replace("<application", `<application android:${key}="${value}"`);
}
writeFileSync(filename, xml);
process.stdout.write("AndroidManifest protegido contra tráfego HTTP e backup automático.\n");
