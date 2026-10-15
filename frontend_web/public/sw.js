/* global self, fetch */
// Instalação como aplicativo web. Nunca armazena cotações, tokens,
// dados de carteira nem respostas da API em cache offline.
self.addEventListener("install", () => { self.skipWaiting(); });
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
self.addEventListener("fetch", (event) => {
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request));
  }
});
