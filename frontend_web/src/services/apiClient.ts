export type ApiErrorCode =
  | "BAD_REQUEST"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "CONFLICT"
  | "RATE_LIMIT"
  | "BAD_GATEWAY"
  | "VALIDATION"
  | "SERVER"
  | "NETWORK"
  | "TIMEOUT"
  | "UNKNOWN";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null,
    public readonly code: ApiErrorCode,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  token?: string | null;
  timeoutMs?: number;
};

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

let unauthorizedHandler: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(),
    options.timeoutMs ?? 10_000,
  );

  const headers = new Headers();
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });

    if (response.status === 204) {
      return undefined as T;
    }

    const payload = await parsePayload(response);
    if (!response.ok) {
      const error = toApiError(response.status, payload);
      if (response.status === 401) {
        unauthorizedHandler?.();
      }
      throw error;
    }

    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("A API demorou demais para responder.", null, "TIMEOUT");
    }
    throw new ApiError(
      "Não foi possível conectar ao backend. Verifique se a API está rodando.",
      null,
      "NETWORK",
    );
  } finally {
    window.clearTimeout(timeout);
  }
}

async function parsePayload(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return undefined;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ApiError("A API retornou uma resposta invalida.", response.status, "UNKNOWN");
  }
}

function toApiError(status: number, payload: unknown): ApiError {
  const message = extractMessage(payload) ?? fallbackMessage(status);
  const codeByStatus: Record<number, ApiErrorCode> = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    429: "RATE_LIMIT",
    422: "VALIDATION",
    500: "SERVER",
    502: "BAD_GATEWAY",
  };
  return new ApiError(message, status, codeByStatus[status] ?? "UNKNOWN", payload);
}

function extractMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map(formatValidationItem).join("; ");
  }
  return null;
}

function formatValidationItem(item: unknown): string {
  if (!item || typeof item !== "object") {
    return String(item);
  }
  const data = item as { loc?: unknown[]; msg?: string };
  const field = Array.isArray(data.loc)
    ? data.loc.filter((part) => part !== "body").join(".")
    : "";
  return field ? `${field}: ${data.msg ?? "valor invalido"}` : data.msg ?? "valor invalido";
}

function fallbackMessage(status: number): string {
  return (
    {
      400: "Requisicao invalida.",
      401: "Sessao expirada. Entre novamente.",
      403: "Você não tem permissão para esta ação.",
      404: "Registro nao encontrado.",
      409: "Conflito ao processar a requisicao.",
      422: "Dados invalidos.",
      500: "Erro interno da API.",
    }[status] ?? `Erro da API (${status}).`
  );
}
