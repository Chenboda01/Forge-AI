export const SPLASH_TEXT = 'Welcome to Forge Desktop Edition';
export const SPLASH_MIN_VISIBLE_MS = 1200;
export const SPLASH_FADE_MS = 450;
export const SPLASH_MAX_VISIBLE_MS = 2600;

export function shouldDismissSplash({ elapsedMs, terminalReady }) {
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return true;
  if (elapsedMs >= SPLASH_MAX_VISIBLE_MS) return true;

  return terminalReady === true && elapsedMs >= SPLASH_MIN_VISIBLE_MS;
}
