export const GLASS_RAINBOW_STOPS = Object.freeze([
  '#ff3b30',
  '#ff9500',
  '#ffd60a',
  '#34c759',
  '#32d6ff',
  '#0a84ff',
]);

export const SPLASH_LOADER_LABEL = 'Starting Forge AI';

export function isSoftwareRenderer(renderer) {
  return /swiftshader|llvmpipe|software|basic render/i.test(
    String(renderer ?? ''),
  );
}

export function glassPerformanceTier({ hardwareConcurrency, renderer } = {}) {
  const limitedCores =
    !Number.isFinite(hardwareConcurrency) || hardwareConcurrency <= 4;
  const unknownRenderer = String(renderer ?? '').trim() === '';

  return limitedCores || unknownRenderer || isSoftwareRenderer(renderer)
    ? 'low'
    : 'high';
}

export function splashLoaderState({ terminalReady } = {}) {
  return terminalReady === true ? 'ready' : 'loading';
}

export function pointerPercent({ clientX, clientY, rect } = {}) {
  const width = rect?.width ?? 0;
  const height = rect?.height ?? 0;

  if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) {
    return { x: 50, y: 50 };
  }

  if (width <= 0 || height <= 0) {
    return { x: 50, y: 50 };
  }

  const clamp = (value) => Math.min(100, Math.max(0, value));

  return {
    x: clamp(((clientX - rect.left) / width) * 100),
    y: clamp(((clientY - rect.top) / height) * 100),
  };
}
