import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..', '..')
const designDocPath = path.join(repoRoot, 'designb.md')
const targetCssPath = path.join(repoRoot, 'frontend', 'src', 'styles', 'design-tokens.css')

const START_MARKER = '<!-- DESIGN_TOKENS_START -->'
const END_MARKER = '<!-- DESIGN_TOKENS_END -->'

const run = async () => {
  const designDoc = await readFile(designDocPath, 'utf8')
  const start = designDoc.indexOf(START_MARKER)
  const end = designDoc.indexOf(END_MARKER)

  if (start === -1 || end === -1 || end <= start) {
    throw new Error('Token markers not found in designb.md.')
  }

  const section = designDoc.slice(start + START_MARKER.length, end).trim()
  const codeMatch = section.match(/```css\s*([\s\S]*?)```/)

  if (!codeMatch?.[1]) {
    throw new Error('No CSS code block found between token markers.')
  }

  const cssBody = codeMatch[1].trim()
  const generated = `/* AUTO-GENERATED FROM designb.md - DO NOT EDIT DIRECTLY */\n${cssBody}\n`
  await writeFile(targetCssPath, generated, 'utf8')
}

run().catch((error) => {
  console.error(`[sync-design-tokens] ${error instanceof Error ? error.message : String(error)}`)
  process.exit(1)
})
