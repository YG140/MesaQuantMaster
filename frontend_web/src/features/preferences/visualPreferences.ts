export type VisualProfile = "compact" | "analytical" | "workstation";
export type VisualPreferences = { profile: VisualProfile; reducedMotion: boolean; transparency: "standard" | "reduced"; fontScale: "standard" | "large" };

export const VISUAL_PREFERENCES_KEY = "mesa_quant_visual_preferences_v1";
export const defaultVisualPreferences: VisualPreferences = { profile: "workstation", reducedMotion: false, transparency: "standard", fontScale: "standard" };

export function readVisualPreferences(): VisualPreferences {
  try {
    const parsed = JSON.parse(localStorage.getItem(VISUAL_PREFERENCES_KEY) ?? "null") as Partial<VisualPreferences> | null;
    if (!parsed) return defaultVisualPreferences;
    return {
      profile: ["compact", "analytical", "workstation"].includes(parsed.profile ?? "") ? parsed.profile! : defaultVisualPreferences.profile,
      reducedMotion: typeof parsed.reducedMotion === "boolean" ? parsed.reducedMotion : defaultVisualPreferences.reducedMotion,
      transparency: ["standard", "reduced"].includes(parsed.transparency ?? "") ? parsed.transparency! : defaultVisualPreferences.transparency,
      fontScale: ["standard", "large"].includes(parsed.fontScale ?? "") ? parsed.fontScale! : defaultVisualPreferences.fontScale,
    };
  } catch { return defaultVisualPreferences; }
}

export function applyVisualPreferences(value: VisualPreferences) {
  const root = document.documentElement;
  root.dataset.visualProfile = value.profile;
  root.dataset.motion = value.reducedMotion ? "reduced" : "standard";
  root.dataset.transparency = value.transparency;
  root.dataset.fontScale = value.fontScale;
}

export function saveVisualPreferences(value: VisualPreferences) {
  localStorage.setItem(VISUAL_PREFERENCES_KEY, JSON.stringify(value));
  applyVisualPreferences(value);
}
