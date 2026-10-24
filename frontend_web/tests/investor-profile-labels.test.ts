import { describe, expect, it } from "vitest";
import {
  investorProfileHorizonLabel,
  investorProfileLiquidityLabel,
  investorProfileRiskLabel,
} from "../src/features/investorProfile/presentation";

describe("rótulos de apresentação do Perfil do Investidor", () => {
  it.each([
    ["menos_1_ano", "Menos de 1 ano"],
    ["1_a_3_anos", "1 a 3 anos"],
    ["3_a_5_anos", "3 a 5 anos"],
    ["5_a_10_anos", "5 a 10 anos"],
    ["mais_10_anos", "Mais de 10 anos"],
    ["longo prazo", "Longo prazo"],
  ])("mostra horizonte %s como %s", (stored, expected) => {
    expect(investorProfileHorizonLabel(stored)).toBe(expected);
  });

  it.each([
    ["Moderado-arrojado", "Moderado a arrojado"],
    ["Moderado-conservador", "Moderado a conservador"],
    ["moderado", "Moderado"],
    ["Arrojado", "Arrojado"],
  ])("mostra classificação %s como %s", (stored, expected) => {
    expect(investorProfileRiskLabel(stored)).toBe(expected);
  });

  it("não inventa classificações nem horizontes desconhecidos", () => {
    expect(investorProfileHorizonLabel("prazo especial")).toBe("prazo especial");
    expect(investorProfileRiskLabel("Perfil experimental")).toBe("Perfil experimental");
    expect(investorProfileHorizonLabel(null)).toBe("Não informado");
    expect(investorProfileRiskLabel(undefined)).toBe("Não informado");
  });

  it("formata necessidade de liquidez sem mudar o valor armazenado", () => {
    expect(investorProfileLiquidityLabel("baixa")).toBe("Baixa");
    expect(investorProfileLiquidityLabel("moderada")).toBe("Moderada");
    expect(investorProfileLiquidityLabel("alta")).toBe("Alta");
  });
});
