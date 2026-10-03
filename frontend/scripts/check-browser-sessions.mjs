import { readFileSync, readdirSync } from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const src = path.resolve('src')
const findings = []
function visit(dir) {
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, ent.name)
    if (ent.isDirectory()) { visit(file); continue }
    if (!/\.tsx?$/.test(file)) continue
    const source = readFileSync(file, 'utf8')
    const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true)
    const add = (node, reason) => findings.push({ file: path.relative(process.cwd(), file),
      line: tree.getLineAndCharacterOfPosition(node.getStart()).line + 1, reason })
    function walk(node) {
      if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression) &&
          ['getItem', 'setItem'].includes(node.expression.name.text)) {
        const key = node.arguments[0]?.getText(tree) ?? ''
        const value = node.arguments[1]?.getText(tree) ?? ''
        if (/(?:token|jwt|credential)/i.test(key) ||
            node.expression.name.text === 'setItem' && /\b(?:[A-Za-z_$]*token|jwt|credentials?)\b/i.test(value))
          add(node, 'browser credential storage forbidden')
      }
      if (file.includes(path.sep + 'api' + path.sep) && /Bearer /.test(node.getText(tree)) &&
          (ts.isStringLiteral(node) || ts.isTemplateExpression(node)))
        add(node, 'browser API Bearer authentication forbidden')
      ts.forEachChild(node, walk)
    }
    walk(tree)
  }
}
visit(src)
const main = readFileSync(path.join(src, 'main.tsx'), 'utf8')
if (!main.includes('installCookieSessionTransport()'))
  findings.push({ file: 'src/main.tsx', line: 1, reason: 'cookie transport must install before rendering' })
if (findings.length) { console.error(JSON.stringify({ findings }, null, 2)); process.exitCode = 1 }
else console.log('Browser session guards passed; no persistent browser credentials.')

