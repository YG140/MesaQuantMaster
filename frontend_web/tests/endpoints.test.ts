import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/services/apiClient", async () => {
  const actual = await vi.importActual<typeof import("../src/services/apiClient")>(
    "../src/services/apiClient",
  );
  return {
    ...actual,
    apiRequest: vi.fn(),
  };
});

import { apiRequest } from "../src/services/apiClient";
import { endpoints } from "../src/services/endpoints/data";

const apiRequestMock = vi.mocked(apiRequest);

describe("endpoints.buildPortfolio", () => {
  beforeEach(() => {
    apiRequestMock.mockClear();
  });

  it("usa timeout dedicado de 120s, sem alterar path, método, token ou payload", async () => {
    apiRequestMock.mockResolvedValueOnce({} as never);
    const payload = {
      available_amount: "10000",
      monthly_contribution: "500",
      objective: "crescimento",
      horizon: "longo prazo",
      risk_profile: "moderado",
      max_assets: 10,
    } as never;

    await endpoints.buildPortfolio("test-token", payload);

    expect(apiRequestMock).toHaveBeenCalledTimes(1);
    expect(apiRequestMock).toHaveBeenCalledWith("/intelligence/build-portfolio", {
      method: "POST",
      token: "test-token",
      body: payload,
      timeoutMs: 120_000,
    });
  });

  it("não altera o timeout padrão (10s) usado pelos demais endpoints", async () => {
    apiRequestMock.mockResolvedValueOnce([] as never);

    await endpoints.assets("test-token");

    expect(apiRequestMock).toHaveBeenCalledWith("/assets", { token: "test-token" });
    const options = apiRequestMock.mock.calls[0][1] as { timeoutMs?: number } | undefined;
    expect(options?.timeoutMs).toBeUndefined();
  });
});
