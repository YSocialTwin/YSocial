// Flags string-concatenation chains where a spliced conditional/comparison lost its parentheses
// (e.g. `"a" + x === y ? b : c`). Usage: NODE_PATH=<dir with acorn> node check_js_precedence.mjs file.js ...
import fs from 'fs';
import * as acorn from 'acorn';
import * as walk from 'acorn-walk';
const files = process.argv.slice(2);
const hasStr = n => n.type==='Literal'&&typeof n.value==='string' || n.type==='BinaryExpression'&&n.operator==='+'&&(hasStr(n.left)||hasStr(n.right));
for (const f of files) {
  let src = fs.readFileSync(f,'utf8'), ast;
  try { ast = acorn.parse(src,{ecmaVersion:'latest',sourceType:'script',locations:true,allowHashBang:true}); } catch(e){ console.log(f,'PARSE ERROR',e.message); continue; }
  walk.full(ast, n => {
    if (n.type==='ConditionalExpression' && n.test.type==='BinaryExpression' && n.test.operator==='+' ) console.log(f+':'+n.loc.start.line,'conditional test is a concatenation');
    if (n.type==='BinaryExpression' && ['===','!==','==','!=','<','>','<=','>='].includes(n.operator) && (hasStr(n.left)&&n.left.type==='BinaryExpression') ) console.log(f+':'+n.loc.start.line,'comparison against concatenation');
    if (n.type==='LogicalExpression' && n.left.type==='BinaryExpression' && n.left.operator==='+' && hasStr(n.left) ) console.log(f+':'+n.loc.start.line,'logical op on concatenation');
  });
}
