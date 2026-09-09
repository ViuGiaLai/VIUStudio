import assert from 'node:assert/strict';
import postcss from 'postcss';
import tailwind from 'tailwindcss';
import config from './tailwind.config.js';

const result = await postcss([tailwind({ ...config, content: [{ raw: '<div class="bg-brand/10 border-brand/30 bg-surface/70 p-5"></div>' }] })]).process('@tailwind utilities;', { from: undefined });
for (const selector of ['.bg-brand\\/10', '.border-brand\\/30', '.bg-surface\\/70', '.p-5']) {
  assert.ok(result.css.includes(selector), `Missing theme utility: ${selector}`);
}
assert.ok(result.css.includes('var(--studio-brand)'));
assert.ok(result.css.includes('0.1'));
console.log('Theme opacity and card-spacing regression checks passed.');
