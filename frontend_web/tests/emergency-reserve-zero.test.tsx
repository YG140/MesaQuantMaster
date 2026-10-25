import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { EmergencyReserveBuilder } from "../src/pages/EmergencyReserveBuilder";
import { renderWithProviders } from "./render";
import { server } from "./testServer";

const api = "http://127.0.0.1:8000";

describe("Reserva inicia sempre do zero na interface", () => {
  it("remove o campo e o indicador de valor já guardado e envia zero no cálculo", async () => {
    let submitted: Record<string, unknown> | null = null;
    server.use(
      http.post(`${api}/intelligence/emergency-reserve/plan`, async ({ request }) => {
        submitted = await request.json() as Record<string, unknown>;
        return HttpResponse.json({
          status: "planned",
          basis: "confirmed_profile_policy",
          essential_monthly_expenses: "3500.00",
          target_months: 6,
          target_amount: "21000.00",
          current_reserve: "0.00",
          months_covered: "0.00",
          progress_percentage: "0.00",
          shortfall: "21000.00",
          monthly_available: "1000.00",
          suggested_next_reserve_contribution: "1000.00",
          remaining_next_contribution: "0.00",
          estimated_months_to_goal: 21,
          allocation_targets: [],
          has_relevant_debt: false,
          warnings: [],
        });
      }),
    );
    sessionStorage.setItem("mesa_quant_session", "test-token");
    const user = userEvent.setup();
    renderWithProviders(<EmergencyReserveBuilder />, "/planejar?secao=reserva");

    expect(screen.queryByLabelText("Quanto já tenho na reserva")).not.toBeInTheDocument();
    expect(screen.getByText(/reserva inicial de R\$ 0/)).toBeVisible();

    const expenses = screen.getByLabelText("Despesas essenciais por mês");
    await user.clear(expenses);
    await user.type(expenses, "350000");

    await user.click(screen.getByRole("button", { name: "Montar minha reserva" }));
    await waitFor(() => expect(submitted).not.toBeNull());
    expect(submitted).toMatchObject({
      essential_monthly_expenses: "3500",
      current_reserve: "0",
      monthly_available: "1000",
      income_unstable: false,
    });
    expect(await screen.findByText("Falta guardar")).toBeVisible();
    expect(screen.getByText("R$ 21.000,00")).toBeVisible();
    expect(screen.queryByText("Já guardado (informado)")).not.toBeInTheDocument();
  });
});
