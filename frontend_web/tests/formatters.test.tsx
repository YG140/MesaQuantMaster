import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { CurrencyInput } from "../src/components/ui/CurrencyInput";
import {
  formatCurrencyBR,
  formatPercentBR,
  formatQuantityBR,
  normalizeDecimalForApi,
  parseBrazilianNumber,
} from "../src/utils/formatters";

describe("formatacao brasileira", () => {
  it("formata moeda em reais com duas casas, virgula decimal e ponto de milhar", () => {
    expect(formatCurrencyBR(0)).toBe("R$ 0,00");
    expect(formatCurrencyBR(9)).toBe("R$ 9,00");
    expect(formatCurrencyBR(99.9)).toBe("R$ 99,90");
    expect(formatCurrencyBR(1000)).toBe("R$ 1.000,00");
    expect(formatCurrencyBR(10000.5)).toBe("R$ 10.000,50");
    expect(formatCurrencyBR(1234567.89)).toBe("R$ 1.234.567,89");
  });

  it("formata percentuais sem duplicar simbolo", () => {
    expect(formatPercentBR(0)).toBe("0,00%");
    expect(formatPercentBR(5)).toBe("5,00%");
    expect(formatPercentBR(12.5)).toBe("12,50%");
    expect(formatPercentBR(100)).toBe("100,00%");
  });

  it("formata quantidades sem prefixo monetario e sem casas desnecessarias", () => {
    expect(formatQuantityBR(10)).toBe("10");
    expect(formatQuantityBR(1000)).toBe("1.000");
    expect(formatQuantityBR(10.5)).toBe("10,5");
    expect(formatQuantityBR(1250.75)).toBe("1.250,75");
  });

  it("interpreta numeros brasileiros e decimais de API", () => {
    expect(parseBrazilianNumber("1.234,56")).toBe(1234.56);
    expect(parseBrazilianNumber("1234,56")).toBe(1234.56);
    expect(parseBrazilianNumber("1234.56")).toBe(1234.56);
    expect(parseBrazilianNumber("1.000")).toBe(1000);
    expect(parseBrazilianNumber("-1.234,56")).toBe(-1234.56);
    expect(parseBrazilianNumber("abc")).toBeNull();
    expect(parseBrazilianNumber(null)).toBeNull();
    expect(parseBrazilianNumber(0)).toBe(0);
  });

  it("normaliza decimais para payload da API sem NaN", () => {
    expect(normalizeDecimalForApi("1.234,56")).toBe("1234.56");
    expect(normalizeDecimalForApi("1234,56")).toBe("1234.56");
    expect(normalizeDecimalForApi("1234.56")).toBe("1234.56");
    expect(normalizeDecimalForApi("1.000.000,00")).toBe("1000000");
    expect(normalizeDecimalForApi("abc")).toBe("0");
  });
});

describe("CurrencyInput", () => {
  it("aceita texto do usuario, remove caracteres invalidos e formata apenas ao sair", async () => {
    const user = userEvent.setup();
    render(<CurrencyInputHarness />);

    const input = screen.getByLabelText("Preco de compra");
    expect(input).toHaveAttribute("type", "text");
    expect(input).toHaveAttribute("inputmode", "decimal");
    expect(input).toHaveAttribute("placeholder", "R$ 0,00");

    await user.type(input, "abc1000,5x");
    expect(input).toHaveValue("1000,5");

    fireEvent.blur(input);
    expect(input).toHaveValue("1.000,50");
  });

  it("aceita valor colado com milhar e normaliza para API", () => {
    render(<CurrencyInputHarness />);

    const input = screen.getByLabelText("Preco de compra");
    fireEvent.change(input, { target: { value: "1.000,50" } });
    expect(input).toHaveValue("1.000,50");
    expect(normalizeDecimalForApi((input as HTMLInputElement).value)).toBe("1000.5");
  });
});

function CurrencyInputHarness() {
  const [value, setValue] = useState("");
  return <CurrencyInput label="Preco de compra" value={value} onChange={(event) => setValue(event.target.value)} />;
}
