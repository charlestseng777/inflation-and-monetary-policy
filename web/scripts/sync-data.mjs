// Copies the JSON the fetcher commits into the site's public directory so the
// app can load it at runtime. Runs automatically before `dev` and `build`.
import { cp, mkdir, access } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const source = join(here, '..', '..', 'data')
const target = join(here, '..', 'public', 'data')

const files = ['timeseries.json', 'meta.json', 'commentary.json']

await mkdir(target, { recursive: true })

let copied = 0
for (const file of files) {
  const from = join(source, file)
  try {
    await access(from)
  } catch {
    console.warn(`[sync-data] ${file} not found in /data — skipping`)
    continue
  }
  await cp(from, join(target, file))
  copied += 1
}

if (copied === 0) {
  // Not fatal: when VITE_API_BASE_URL is set the app reads from the API and
  // never touches these files. Only a local build with no API needs them.
  console.warn('[sync-data] No data files found in /data.')
  console.warn('            Fine if VITE_API_BASE_URL points at the API service.')
  console.warn('            Otherwise run: python fetcher/fetch.py --no-llm')
} else {
  console.log(`[sync-data] copied ${copied} file(s) into web/public/data`)
}
