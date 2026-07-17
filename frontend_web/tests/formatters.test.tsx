import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { CurrencyInput } from "../src/components/forms/CurrencyInput";
import { DecimalInput } from "../src/components/forms/DecimalInput";
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
  it("comeca em 0,00 e desloca centavos ao digitar", async () => {
    const user = userEvent.setup();
    render(<CurrencyInputHarness />);

    const input = screen.getByLabelText("Preco de compra");
    expect(input).toHaveAttribute("type", "text");
    expect(input).toHaveAttribute("inputmode", "numeric");
    expect(input).toHaveValue("0,00");

    await user.type(input, "1");
    expect(input).toHaveValue("0,01");
    await user.type(input, "2");
    expect(input).toHaveValue("0,12");
    await user.type(input, "3");
    expect(input).toHaveValue("1,23");
    await user.type(input, "4");
    expect(input).toHaveValue("12,34");
    await user.type(input, "5");
    expect(input).toHaveValue("123,45");
    await user.type(input, "6");
    expect(input).toHaveValue("1.234,56");
  });

  it("backspace desloca os centavos no sentido inverso", async () => {
    const user = userEvent.setup();
    render(<CurrencyInputHarness />);

    const input = screen.getByLabelText("Preco de compra");
    await user.type(input, "123456");
    expect(input).toHaveValue("1.234,56");

    await user.keyboard("{Backspace}");
    expect(input).toHaveValue("123,45");
    await user.keyboard("{Backspace}");
    expect(input).toHaveValue("12,34");
    await user.keyboard("{Backspace}");
    expect(input).toHaveValue("1,23");
    await user.keyboard("{Backspace}");
    expect(input).toHaveValue("0,12");
    await user.keyboard("{Backspace}");
    expect(input).toHaveValue("0,01");
    await user.keyboard("{Backspace}");
    expect(input).toHaveValue("0,00");
  });

  it("cola formatos brasileiros, moeda e decimal de API", () => {
    const values = ["1.234,56", "R$ 1.234,56", "1234,56", "1234.56"];

    for (const pasted of values) {
      render(<CurrencyInputHarness />);
      const input = screen.getByLabelText("Preco de compra");
      fireEvent.paste(input, {
        clipboardData: {
          getData: () => pasted,
        },
      });
      expect(input).toHaveValue("1.234,56");
      expect(normalizeDecimalForApi((input as HTMLInputElement).value)).toBe("1234.56");
      document.body.innerHTML = "";
    }
  });

  it("ignora caracteres nao numericos sem produzir NaN", async () => {
    const user = userEvent.setup();
    render(<CurrencyInputHarness />);

    const input = screen.getByLabelText("Preco de compra");
    await user.type(input, "abc1x2");

    expect(input).toHaveValue("0,12");
    expect(normalizeDecimalForApi((input as HTMLInputElement).value)).not.toBe("NaN");
  });

  it("taxas e impostos usam a mesma mascara", async () => {
    const user = userEvent.setup();
    render(
      <>
        <CurrencyInputHarness label="Taxas" />
        <CurrencyInputHarness label="Impostos" />
      </>,
    );

    await user.type(screen.getByLabelText("Taxas"), "1234");
    await user.type(screen.getByLabelText("Impostos"), "56");

    expect(screen.getByLabelText("Taxas")).toHaveValue("12,34");
    expect(screen.getByLabelText("Impostos")).toHaveValue("0,56");
  });

  it("normaliza payload monetario sem erro de precisao por float", () => {
    expect(normalizeDecimalForApi("0,10")).toBe("0.1");
    expect(normalizeDecimalForApi("0,20")).toBe("0.2");
    expect(normalizeDecimalForApi("1.234,56")).toBe("1234.56");
  });
});

describe("DecimalInput", () => {
  it("quantidade nao usa mascara monetaria e preserva 0,003", async () => {
    const user = userEvent.setup();
    render(<DecimalInputHarness />);

    const input = screen.getByLabelText("Quantidade");
    await user.type(input, "0,003");

    expect(input).toHaveValue("0,003");
    expect(normalizeDecimalForApi((input as HTMLInputElement).value)).toBe("0.003");
  });
});

function CurrencyInputHarness({ label = "Preco de compra" }: { label?: string }) {
  const [value, setValue] = useState("");
  return <CurrencyInput label={label} value={value} onChange={(event) => setValue(event.target.value)} />;
}

function DecimalInputHarness() {
  const [value, setValue] = useState("");
  return <DecimalInput label="Quantidade" value={value} onChange={(event) => setValue(event.target.value)} />;
}
