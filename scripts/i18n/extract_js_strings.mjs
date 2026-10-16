// Collect text of data-driven JS (guided tutorials): string/template values of the
// given property names. Writes y_web/translations/js/<domain>/en.json (key = text).
// Usage: NODE_PATH=<acorn dir> node extract_js_strings.mjs <domain> <props,comma> file.js ...
import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';
const require = createRequire(process.env.NODE_PATH ? process.env.NODE_PATH + '/' : import.meta.url);
const acorn = require('acorn');
const walk = require('acorn-walk');
const [domain, props, ...files] = process.argv.slice(2);
const names = new Set(props.split(','));
const out = {};
for (const f of files) {
  const src = fs.readFileSync(f, 'utf8');
  const ast = acorn.parse(src, { ecmaVersion: 'latest', sourceType: 'script' });
  walk.full(ast, (n) => {
    if (n.type !== 'Property' || n.computed) return;
    const k = n.key.name || n.key.value;
    if (!names.has(k)) return;
    let v = n.value, s = null;
    if (v.type === 'Literal' && typeof v.value === 'string') s = v.value;
    else if (v.type === 'TemplateLiteral' && v.expressions.length === 0) s = v.quasis[0].value.cooked;
    if (s && (s.match(/[A-Za-z]{2}/g) || []).length) out[s] = s;
  });
}
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..', 'y_web', 'translations', 'js', domain);
fs.mkdirSync(root, { recursive: true });
const sorted = Object.fromEntries(Object.entries(out).sort(([a], [b]) => (a < b ? -1 : 1)));
fs.writeFileSync(path.join(root, 'en.json'), JSON.stringify(sorted, null, 2) + '\n');
console.log(Object.keys(sorted).length, 'strings,', fs.statSync(path.join(root, 'en.json')).size, 'bytes');
