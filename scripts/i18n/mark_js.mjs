// Wrap user-facing JS literals in YI18n.t('English text', {name: expr}).
// Usage: NODE_PATH=<dir with acorn> node mark_js.mjs [--dry] file.js ...
// Handles alert/confirm/prompt(arg), X.textContent|innerText|title|placeholder = value,
// setAttribute('title'|'placeholder'|'aria-label'|'alt', value). A value may be a
// string literal, a template literal, a '+' chain with literals, or a conditional.
import fs from 'fs';
import { createRequire } from 'module';
const require = createRequire(process.env.NODE_PATH ? process.env.NODE_PATH + '/' : import.meta.url);
const acorn = require('acorn');
const walk = require('acorn-walk');

const SETTERS = new Set(['textContent', 'innerText', 'title', 'placeholder', 'ariaLabel']);
const ATTRS = new Set(['title', 'placeholder', 'aria-label', 'alt']);
const CALLS = new Set(['alert', 'confirm', 'prompt', 'showToast', 'showLoading', 'showHpcMonitorMessage', 'showTelemetryMessage']);
const dry = process.argv.includes('--dry');
const noHtml = process.argv.includes('--no-html'); // skip the generic HTML-literal rule (step data holds HTML too)
const noProps = process.argv.includes('--no-props'); // skip object-property rules (data-driven text is translated at render time)
const files = process.argv.slice(2).filter((a) => !a.startsWith('--'));

function hasText(s) { return (s.match(/[A-Za-z]/g) || []).length >= 2; }
function quote(s) { return "'" + s.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n') + "'"; }
function pname(n, src) {
  let name = null;
  if (n.type === 'Identifier') name = n.name;
  else if (n.type === 'MemberExpression') name = n.computed ? (n.property.type === 'Literal' ? String(n.property.value) : pname(n.object, src)) : n.property.name;
  else if (n.type === 'CallExpression') {
    const c = n.callee;
    const fn = c.type === 'Identifier' ? c.name : (c.property && c.property.name);
    if (['String', 'Number', 'parseInt', 'parseFloat'].includes(fn) && n.arguments[0]) return pname(n.arguments[0], src);
    name = fn;
  } else if (n.type === 'LogicalExpression' || n.type === 'BinaryExpression') return pname(n.left, src);
  name = (name || 'value').replace(/\W+/g, '_').replace(/^_+|_+$/g, '').toLowerCase() || 'value';
  if (/^\d/.test(name)) name = 'v' + name;
  return name.slice(0, 24);
}

// Returns {key, params:[[name, srcText]]} or null.
function build(node, src) {
  const parts = []; // {lit} or {expr}
  function flatten(n) {
    if (n.type === 'Literal' && typeof n.value === 'string') parts.push({ lit: n.value });
    else if (n.type === 'TemplateLiteral') {
      n.quasis.forEach((q, i) => {
        parts.push({ lit: q.value.cooked });
        if (i < n.expressions.length) parts.push({ expr: n.expressions[i] });
      });
    } else if (n.type === 'BinaryExpression' && n.operator === '+') {
      // Only treat as text concatenation if at least one side is a string/template.
      if (!containsStr(n)) { parts.push({ expr: n }); return; }
      flatten(n.left); flatten(n.right);
    } else parts.push({ expr: n });
  }
  function containsStr(n) {
    if (n.type === 'Literal' && typeof n.value === 'string') return true;
    if (n.type === 'TemplateLiteral') return true;
    if (n.type === 'BinaryExpression' && n.operator === '+') return containsStr(n.left) || containsStr(n.right);
    return false;
  }
  flatten(node);
  const names = new Map();
  let key = '';
  const params = [];
  for (const p of parts) {
    if ('lit' in p) {
      if (/\{\w+\}/.test(p.lit)) return null;
      key += p.lit;
    } else {
      const text = src.slice(p.expr.start, p.expr.end);
      let nm = names.get(text);
      if (!nm) {
        const base = pname(p.expr, src); nm = base; let i = 2;
        while ([...names.values()].includes(nm)) nm = base + i++;
        names.set(text, nm); params.push([nm, text]);
      }
      key += '{' + nm + '}';
    }
  }
  if (key.includes('__J') || !hasText(key.replace(/\{\w+\}/g, ''))) return null;
  return { key, params };
}

function render(b) {
  let out = 'YI18n.t(' + quote(b.key);
  if (b.params.length) out += ', {' + b.params.map(([n, t]) => (n === t ? n : n + ': ' + t)).join(', ') + '}';
  return out + ')';
}

function targets(node, src, add) {
  // conditional: recurse on branches
  if (node.type === 'ConditionalExpression') {
    targets(node.consequent, src, add); targets(node.alternate, src, add); return;
  }
  if (node.type === 'LogicalExpression') { targets(node.right, src, add); return; }
  const isStr = (n) => (n.type === 'Literal' && typeof n.value === 'string') || n.type === 'TemplateLiteral' ||
    (n.type === 'BinaryExpression' && n.operator === '+');
  if (!isStr(node)) return;
  const b = build(node, src);
  if (b) add(node, b);
}


// HTML-aware: wrap text runs of an HTML string built from literals/templates/concats.
function buildHtml(node, src) {
  const parts = [];
  function containsStr(n) {
    if (n.type === 'Literal' && typeof n.value === 'string') return true;
    if (n.type === 'TemplateLiteral') return true;
    if (n.type === 'BinaryExpression' && n.operator === '+') return containsStr(n.left) || containsStr(n.right);
    return false;
  }
  function flatten(n) {
    if (n.type === 'Literal' && typeof n.value === 'string') parts.push({ lit: n.value });
    else if (n.type === 'TemplateLiteral') {
      n.quasis.forEach((q, i) => { parts.push({ lit: q.value.cooked }); if (i < n.expressions.length) parts.push({ expr: n.expressions[i] }); });
    } else if (n.type === 'BinaryExpression' && n.operator === '+' && containsStr(n)) { flatten(n.left); flatten(n.right); }
    else parts.push({ expr: n });
  }
  flatten(node);
  const exprs = [];
  let pseudo = '';
  for (const p of parts) {
    if ('lit' in p) pseudo += p.lit; else { exprs.push(p.expr); pseudo += '\u0001' + (exprs.length - 1) + '\u0002'; }
  }
  if (/<style|<script/i.test(pseudo)) return null;
  const out = []; // JS source pieces
  let changed = false, last = 0;
  const push = (lit) => { if (lit) out.push(quote(lit)); };
  const hasTags = /<[a-z]/i.test(pseudo);
  const runRe = /(^|>)([^<>]*)(?=<|$)/g;
  let m;
  const pieces = [];
  while (hasTags && (m = runRe.exec(pseudo)) !== null) {
    const start = m.index + m[1].length, text = m[2];
    if (m[0] === '' ) { runRe.lastIndex++; continue; }
    const bare = text.replace(/\u0001\d+\u0002/g, '');
    if (!hasText(bare) || bare.includes('__J') || /^\s*&[a-z]+;\s*$/.test(bare)) continue;
    const lead = text.match(/^\s*/)[0], trail = text.match(/\s*$/)[0];
    const core = text.slice(lead.length, text.length - trail.length);
    if (!core || /\{\w+\}/.test(core)) continue;
    pieces.push({ s: start + lead.length, e: start + text.length - trail.length, core });
  }
  const attrRe = /\b(?:title|placeholder|alt|aria-label|data-tooltip)="([^"<>]*)"/g;
  while ((m = attrRe.exec(pseudo)) !== null) {
    const text = m[1]; const start = m.index + m[0].indexOf('"') + 1;
    const bare = text.replace(/\u0001\d+\u0002/g, '');
    if (!hasText(bare) || bare.includes('__J')) continue;
    if (/\{\w+\}/.test(text)) continue;
    pieces.push({ s: start, e: start + text.length, core: text });
  }
  pieces.sort((a, b) => a.s - b.s);
  if (!pieces.length) return null;
  const names = new Map();
  // An expression spliced into a '+' chain must keep its own precedence: `${a ? b : c}` -> `(a ? b : c)`.
  const SIMPLE = new Set(['Identifier', 'MemberExpression', 'CallExpression', 'Literal', 'TemplateLiteral', 'ThisExpression', 'ArrayExpression', 'ObjectExpression']);
  function paren(ex) { const t = src.slice(ex.start, ex.end); return SIMPLE.has(ex.type) ? t : '(' + t + ')'; }
  function expand(seg) { // static pseudo segment -> JS pieces (literal text + expr refs)
    const res = []; let i = 0; const re = /\u0001(\d+)\u0002/g; let mm;
    while ((mm = re.exec(seg)) !== null) { if (mm.index > i) res.push(quote(seg.slice(i, mm.index))); res.push(paren(exprs[+mm[1]])); i = mm.index + mm[0].length; }
    if (i < seg.length) res.push(quote(seg.slice(i)));
    return res;
  }
  let pos = 0;
  for (const p of pieces) {
    out.push(...expand(pseudo.slice(pos, p.s)));
    // key with placeholders
    const pm = new Map(); const params = []; let key = '';
    let i = 0; const re = /\u0001(\d+)\u0002/g; let mm;
    const addTxt = (t) => { key += t; };
    while ((mm = re.exec(p.core)) !== null) {
      addTxt(p.core.slice(i, mm.index));
      const ex = exprs[+mm[1]]; const text = src.slice(ex.start, ex.end);
      let nm = pm.get(text);
      if (!nm) { const base = pname(ex, src); nm = base; let k = 2; while ([...pm.values()].includes(nm)) nm = base + k++; pm.set(text, nm); params.push([nm, text]); }
      key += '{' + nm + '}'; i = mm.index + mm[0].length;
    }
    addTxt(p.core.slice(i));
    out.push(render({ key, params }));
    pos = p.e; changed = true;
  }
  out.push(...expand(pseudo.slice(pos)));
  return out.filter((x) => x !== "''").join(' + ');
}

const PROPS = new Set(['label', 'text', 'message', 'placeholder', 'description', 'hint', 'tooltip', 'emptyMessage', 'name', 'title']);
const COLS = new Set(['id', 'sort', 'formatter', 'width']);
let parents = new Map();
function htmlSkip(n) { return false; }
function looksText(v) { return /^[A-Z0-9✓●✗⚠]/.test(v) || /\s/.test(v); }
let propTargets = () => {};
let total = 0;
function sanitize(t) {
  // Same-length masking of Jinja so the script parses; offsets stay valid.
  return t.replace(/\{\{[\s\S]*?\}\}/g, (m) => '__J' + '_'.repeat(Math.max(0, m.length - 3)))
          .replace(/\{%[\s\S]*?%\}/g, (m) => m.length >= 4 ? '/*' + ' '.repeat(m.length - 4) + '*/' : ' '.repeat(m.length))
          .replace(/\{#[\s\S]*?#\}/g, (m) => m.length >= 4 ? '/*' + ' '.repeat(m.length - 4) + '*/' : ' '.repeat(m.length));
}
function transform(src, f) {
  let ast;
  try { ast = acorn.parse(sanitize(src), { ecmaVersion: 'latest', sourceType: 'script', allowHashBang: true }); }
  catch (e) { console.error('PARSE FAIL', f, e.message); return null; }
  const edits = [];
  const add = (node, b) => edits.push([node.start, node.end, render(b)]);
  walk.full(ast, (n) => { if (n.type === 'ObjectExpression') for (const p of n.properties) parents.set(p, n); });
  propTargets = (p, okey) => {
    const v = p.value;
    if (okey === 'name' || okey === 'title') {
      const sibs = (parents.get(p)?.properties || []).map((q) => q.key && (q.key.name || q.key.value));
      if (okey === 'name' && !sibs.some((k) => COLS.has(k))) return;
      if (okey === 'title' && v.type !== 'Literal' && v.type !== 'TemplateLiteral') return;
    }
    if (v.type === 'Literal' && typeof v.value === 'string' && !looksText(v.value)) return;
    targets(v, src, add);
  };
  walk.full(ast, (n) => {
    if (n.type === 'CallExpression') {
      const c = n.callee;
      const name = c.type === 'Identifier' ? c.name : (c.type === 'MemberExpression' && c.object.name === 'window' ? c.property.name : null);
      if (CALLS.has(name) && n.arguments[0]) targets(n.arguments[0], src, add);
      if (c.type === 'MemberExpression' && c.property.name === 'setAttribute' && n.arguments.length === 2 &&
          n.arguments[0].type === 'Literal' && ATTRS.has(n.arguments[0].value)) targets(n.arguments[1], src, add);
    } else if (n.type === 'AssignmentExpression' && n.operator === '=' && n.left.type === 'MemberExpression' &&
               !n.left.computed && SETTERS.has(n.left.property.name)) {
      targets(n.right, src, add);
    } else if (!noProps && n.type === 'Property' && !n.computed && n.value && (PROPS.has(n.key.name || n.key.value))) {
      const okey = n.key.name || n.key.value;
      if (okey === 'name') {
        // only for column-like objects (gridjs: id/sort/formatter/width)
        const sib = new Set(); // determined via parent below
      }
      propTargets(n, okey);
    } else if (n.type === 'NewExpression' && n.callee.name === 'Error' && n.arguments[0]) {
      targets(n.arguments[0], src, add);
    } else if (n.type === 'BinaryExpression' && (n.operator === '===' || n.operator === '!==') && n.right.type === 'Literal' &&
               typeof n.right.value === 'string' && n.left.type === 'MemberExpression' && n.left.property.name === 'label') {
      targets(n.right, src, add);
    } else if (n.type === 'ReturnStatement' && n.argument && (n.argument.type === 'BinaryExpression' || n.argument.type === 'Literal' || n.argument.type === 'TemplateLiteral')) {
      const b = build(n.argument, src);
      if (b && /^[A-Z][A-Za-z]+( [A-Za-z]+)*[:(!.?]?( |$)/.test(b.key) && !/[<>\/=]/.test(b.key) && b.key.length < 80) add(n.argument, b);
    } else if (!noHtml && (n.type === 'TemplateLiteral' || n.type === 'Literal' && typeof n.value === 'string' || (n.type === 'BinaryExpression' && n.operator === '+')) &&
               /<[a-z]|\b(?:title|placeholder|alt|aria-label)="/i.test(src.slice(n.start, n.end)) && src.slice(Math.max(0, n.start - 8), n.start) !== 'YI18n.t(' && !htmlSkip(n)) {
      const r = buildHtml(n, src); if (r) edits.push([n.start, n.end, r]);
    } else if (n.type === 'AssignmentExpression' && (n.operator === '=' || n.operator === '+=') && n.left.type === 'MemberExpression' &&
               !n.left.computed && n.left.property.name === 'innerHTML') {
      const hv = (x) => {
        if (x.type === 'ConditionalExpression') { hv(x.consequent); hv(x.alternate); return; }
        const r = buildHtml(x, src); if (r) edits.push([x.start, x.end, r]);
      };
      hv(n.right);
    } else if (n.type === 'CallExpression' && n.callee.type === 'MemberExpression' && n.callee.property.name === 'insertAdjacentHTML' && n.arguments[1]) {
      const r = buildHtml(n.arguments[1], src); if (r) edits.push([n.arguments[1].start, n.arguments[1].end, r]);
    }
  });
  // drop edits nested inside others (keep outermost)
  edits.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
  const kept = [];
  for (const e of edits) if (!kept.length || e[0] >= kept[kept.length - 1][1]) kept.push(e);
  let out = src;
  for (const [s, e, r] of kept.reverse()) out = out.slice(0, s) + r + out.slice(e);
  return { out, count: kept.length };
}

for (const f of files) {
  const text = fs.readFileSync(f, 'utf8');
  let out = text, count = 0;
  if (f.endsWith('.html')) {
    const re = /(<script(?![^>]*\bsrc=)[^>]*>)([\s\S]*?)(<\/script>)/gi;
    let m, res = '', last = 0;
    while ((m = re.exec(text)) !== null) {
      const body = m[2];
      if (/type=["'](?!text\/javascript)/i.test(m[1]) || !body.trim()) continue;
      const r = transform(body, f + '@' + m.index);
      if (r && r.count) { res += text.slice(last, m.index + m[1].length) + r.out; last = m.index + m[1].length + body.length; count += r.count; }
    }
    out = res + text.slice(last);
  } else {
    const r = transform(text, f);
    if (r) { out = r.out; count = r.count; }
  }
  if (count) {
    total += count; console.log(f, count);
    if (!dry) fs.writeFileSync(f, out);
  }
}
console.log('total', total);
