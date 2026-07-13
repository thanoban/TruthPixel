// Design tokens ported from the claude.ai/design "TruthPixel.dc.html" mockup's getTheme().
// Kept in sync manually with dashboard/app/theme.ts — same convention as types.ts, which
// already documents "keep in sync manually until an OpenAPI codegen step exists."
export const darkTokens = {
  bg: "oklch(14% 0.014 260)",
  surface: "oklch(19% 0.016 260)",
  surface2: "oklch(23% 0.018 260)",
  border: "oklch(32% 0.016 260)",
  borderStrong: "oklch(45% 0.02 260)",
  text: "oklch(93% 0.006 260)",
  textMuted: "oklch(64% 0.012 260)",
  textFaint: "oklch(48% 0.012 260)",
  accent: "oklch(78% 0.14 195)",
  accentText: "oklch(14% 0.014 260)",
  danger: "oklch(72% 0.19 25)",
  warn: "oklch(78% 0.15 85)",
  safe: "oklch(72% 0.15 150)",
};

export const lightTokens = {
  bg: "oklch(96% 0.007 95)",
  surface: "oklch(99% 0.003 95)",
  surface2: "oklch(94% 0.008 95)",
  border: "oklch(80% 0.012 95)",
  borderStrong: "oklch(60% 0.02 95)",
  text: "oklch(20% 0.012 260)",
  textMuted: "oklch(42% 0.014 260)",
  textFaint: "oklch(55% 0.012 260)",
  accent: "oklch(46% 0.14 195)",
  accentText: "oklch(99% 0.003 95)",
  danger: "oklch(50% 0.19 25)",
  warn: "oklch(48% 0.15 85)",
  safe: "oklch(42% 0.14 150)",
};

export type ThemeTone = "danger" | "warn" | "safe";

// Matches backend/app/schemas.py's needs_review threshold semantics: >=0.66 is the mockup's
// own "high" band, 0.35 is this codebase's existing review threshold.
export function riskToneName(score: number): ThemeTone {
  if (score >= 0.66) return "danger";
  if (score >= 0.35) return "warn";
  return "safe";
}

export function riskStamp(score: number): string {
  if (score >= 0.66) return "FLAGGED";
  if (score >= 0.35) return "REVIEW";
  return "CLEARED";
}

export const THEME_STORAGE_KEY = "truthpixel-theme";

// Inlined into layout.tsx's <head> as a blocking script so the correct theme is set before
// first paint — avoids a flash of the wrong theme on load. Must stay a plain string (no
// external variables) since it runs before React hydrates.
export const noFlashThemeScript = `
(function () {
  try {
    var stored = localStorage.getItem('${THEME_STORAGE_KEY}');
    var theme = stored === 'light' || stored === 'dark'
      ? stored
      : (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    document.documentElement.setAttribute('data-theme', theme);
  } catch (e) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();
`;
