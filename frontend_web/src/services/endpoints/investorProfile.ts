import { apiRequest } from "../apiClient";
import type {
  InvestorProfile,
  InvestorProfileAnswers,
  InvestorProfileEvaluation,
  InvestorProfileStatusResponse,
} from "../../types/api";

export const investorProfileEndpoints = {
  status: (token: string) =>
    apiRequest<InvestorProfileStatusResponse>("/investor-profile/status", { token }),
  get: (token: string) =>
    apiRequest<InvestorProfile>("/investor-profile", { token }),
  saveAnswers: (token: string, payload: InvestorProfileAnswers) =>
    apiRequest<InvestorProfile>("/investor-profile/answers", {
      method: "PUT",
      token,
      body: payload,
    }),
  evaluate: (token: string) =>
    apiRequest<InvestorProfileEvaluation>("/investor-profile/evaluate", {
      method: "POST",
      token,
    }),
  confirm: (token: string) =>
    apiRequest<InvestorProfile>("/investor-profile/confirm", {
      method: "POST",
      token,
    }),
  review: (token: string) =>
    apiRequest<InvestorProfile>("/investor-profile/review", {
      method: "POST",
      token,
    }),
};
