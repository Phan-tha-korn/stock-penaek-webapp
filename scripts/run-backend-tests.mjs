import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const candidates = [
  path.join(root, '.venv', 'Scripts', 'python.exe'),
  path.join(root, '.venv', 'bin', 'python'),
  'python',
  'python3',
]

const python = candidates.find((candidate) => candidate === 'python' || candidate === 'python3' || existsSync(candidate))

if (!python) {
  console.error('Python interpreter not found.')
  process.exit(1)
}

const result = spawnSync(
  python,
  ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v'],
  {
    cwd: root,
    env: {
      ...process.env,
      PYTHONPATH: root,
    },
    stdio: 'inherit',
  },
)

if (result.error) {
  console.error(result.error.message)
  process.exit(1)
}

process.exit(result.status ?? 1)
