import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const read = (relative) =>
  readFileSync(new URL(relative, import.meta.url), 'utf8');

const template = read('../build/desktop.ejs');
const appImageDesktop = read('../build/forge-ai-desktop.desktop');
const config = read('../forge.config.mjs');
const pkg = JSON.parse(read('../package.json'));
const main = read('../src/main.js');

test('desktop template uses the executable name for WM_CLASS', () => {
  assert.match(template, /^StartupWMClass=<%= name %>$/m);
  assert.doesNotMatch(template, /^StartupWMClass=<%= productName %>$/m);
});

test('desktop template points at the installed desktop file name', () => {
  assert.match(template, /^Name=<%= productName %>$/m);
  assert.ok(template.includes('Exec=<%= name %> %U'));
  assert.match(template, /^Icon=<%= name %>$/m);
});

test('desktop template renders forge-ai-desktop as the startup class', () => {
  const rendered = template
    .replaceAll('<%= name %>', 'forge-ai-desktop')
    .replaceAll('<%= productName %>', 'Forge AI Desktop');

  assert.match(rendered, /^Name=Forge AI Desktop$/m);
  assert.ok(rendered.includes('Exec=forge-ai-desktop %U'));
  assert.match(rendered, /^Icon=forge-ai-desktop$/m);
  assert.match(rendered, /^StartupWMClass=forge-ai-desktop$/m);
});

test('package.json declares the installed desktop file name', () => {
  assert.equal(pkg.desktopName, 'forge-ai-desktop.desktop');
  assert.equal(pkg.name, 'forge-ai-desktop');
});

test('forge config applies the custom template to deb and rpm', () => {
  assert.match(config, /const desktopTemplate = path\.resolve\(/);
  assert.equal((config.match(/desktopTemplate,/g) ?? []).length, 2);
});

test('AppImage desktop entry matches the deb/rpm launcher identity', () => {
  assert.match(appImageDesktop, /^Name=Forge AI Desktop$/m);
  assert.ok(appImageDesktop.includes('Exec=forge-ai-desktop %U'));
  assert.match(appImageDesktop, /^Icon=forge-ai-desktop$/m);
  assert.match(appImageDesktop, /^StartupWMClass=forge-ai-desktop$/m);
  assert.match(appImageDesktop, /^Categories=Development;$/m);
});

test('forge config passes the desktop entry to the AppImage maker', () => {
  assert.match(config, /const appImageDesktop = path\.resolve\(/);
  assert.match(config, /desktopFile: appImageDesktop/);
});

test('deb/rpm declare a single main category', () => {
  assert.equal(
    (config.match(/categories: \['Development'\]/g) ?? []).length,
    2,
  );
  assert.doesNotMatch(config, /categories: \[[^\]]*'Utility'/);
});

test('main process sets the desktop identity before Chromium starts', () => {
  assert.match(main, /app\.setDesktopName\('forge-ai-desktop\.desktop'\)/);
  assert.ok(
    main.indexOf('app.setDesktopName(') < main.indexOf('app.whenReady()'),
    'setDesktopName must run before app.whenReady()',
  );
  assert.doesNotMatch(main, /whenReady\(\)\.then\(\(\) => \{\s*app\.setName/);
});
