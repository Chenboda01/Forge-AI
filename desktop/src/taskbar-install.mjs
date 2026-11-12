import fs from 'node:fs';
import path from 'node:path';
import { randomBytes } from 'node:crypto';

export function installAppImageFile({ source, target, applicationsDir }) {
  const directory = path.resolve(applicationsDir);
  const resolvedTarget = path.resolve(target);
  const resolvedSource = path.resolve(source);

  if (path.dirname(resolvedTarget) !== directory) {
    throw new Error('Refusing to write outside the applications directory');
  }

  if (!fs.existsSync(resolvedSource)) {
    throw new Error(`The running AppImage is missing: ${resolvedSource}`);
  }

  if (resolvedSource === resolvedTarget) {
    fs.chmodSync(resolvedTarget, 0o755);

    return { copied: false, path: resolvedTarget };
  }

  fs.mkdirSync(directory, { recursive: true, mode: 0o755 });

  const temporary = path.join(
    directory,
    `.${path.basename(resolvedTarget)}.${randomBytes(6).toString('hex')}.tmp`,
  );

  try {
    fs.copyFileSync(resolvedSource, temporary);
    fs.chmodSync(temporary, 0o755);
    fs.renameSync(temporary, resolvedTarget);
  } catch (error) {
    try {
      fs.rmSync(temporary, { force: true });
    } catch {
      // The temporary file is best-effort cleanup; the original error matters.
    }

    throw error;
  }

  return { copied: true, path: resolvedTarget };
}
