import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Tailwind's PostCSS plugin resolves `tailwind.config.js` relative to
// process.cwd(), which is not necessarily this directory — running vite from
// the repo root silently loads an empty config and strips every utility class.
// Pin it to an absolute path so the build is cwd-independent.
const here = dirname(fileURLToPath(import.meta.url))

export default {
  plugins: {
    tailwindcss: { config: join(here, 'tailwind.config.js') },
    autoprefixer: {},
  },
}
