import { spawn } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import net from 'node:net'
import { chromium } from 'playwright'

const projectRoot = path.resolve(import.meta.dirname, '..')
const actionsFile = path.join(projectRoot, 'e2e', 'actions', 'layout-smoke.json')
const outputDir = path.join(projectRoot, 'artifacts', 'ui-e2e', 'latest')
const anchorId = process.env.UI_E2E_ANCHOR ?? 'anchor-01-self-draw'
const internalHost = process.env.UI_E2E_HOST ?? '127.0.0.1'
const internalPort = Number.parseInt(process.env.UI_E2E_PORT ?? '4173', 10)
const defaultUrl = `http://${internalHost}:${internalPort}/?anchor=${encodeURIComponent(anchorId)}`
const url = process.env.UI_E2E_URL ?? defaultUrl
const headless = process.env.UI_E2E_HEADLESS !== '0'

function resolveChromiumExecutablePath() {
  const defaultPath = chromium.executablePath()
  if (fs.existsSync(defaultPath)) {
    return defaultPath
  }

  const cacheRoot = path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright')
  if (!fs.existsSync(cacheRoot)) {
    return defaultPath
  }

  const chromiumDirs = fs
    .readdirSync(cacheRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.startsWith('chromium-'))
    .map((entry) => entry.name)
    .sort()
    .reverse()

  for (const dirName of chromiumDirs) {
    const armPath = path.join(
      cacheRoot,
      dirName,
      'chrome-mac-arm64',
      'Google Chrome for Testing.app',
      'Contents',
      'MacOS',
      'Google Chrome for Testing',
    )
    if (fs.existsSync(armPath)) {
      return armPath
    }

    const x64Path = path.join(
      cacheRoot,
      dirName,
      'chrome-mac-x64',
      'Google Chrome for Testing.app',
      'Contents',
      'MacOS',
      'Google Chrome for Testing',
    )
    if (fs.existsSync(x64Path)) {
      return x64Path
    }
  }

  return defaultPath
}

function fail(message) {
  console.error(`[test:e2e:ui] ${message}`)
  process.exit(1)
}

function isPortOpen(host, port) {
  return new Promise((resolve) => {
    const socket = new net.Socket()
    socket.setTimeout(250)
    socket.once('connect', () => {
      socket.destroy()
      resolve(true)
    })
    const close = () => {
      socket.destroy()
      resolve(false)
    }
    socket.once('timeout', close)
    socket.once('error', close)
    socket.connect(port, host)
  })
}

async function waitForServer(host, port, timeoutMs = 30000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (await isPortOpen(host, port)) {
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 200))
  }
  throw new Error(`Timed out waiting for server on ${host}:${port}`)
}

function startLocalServer(host, port) {
  const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm'
  const child = spawn(
    npmCmd,
    ['run', 'dev', '--', '--host', host, '--port', String(port), '--strictPort'],
    {
      cwd: projectRoot,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, CI: process.env.CI ?? '1' },
    },
  )

  child.stdout.on('data', (chunk) => {
    process.stdout.write(`[vite] ${chunk}`)
  })
  child.stderr.on('data', (chunk) => {
    process.stderr.write(`[vite] ${chunk}`)
  })

  return child
}

function loadSteps() {
  if (!fs.existsSync(actionsFile)) {
    fail(`Actions file not found: ${actionsFile}`)
  }
  const payload = JSON.parse(fs.readFileSync(actionsFile, 'utf-8'))
  const steps = Array.isArray(payload) ? payload : payload.steps
  if (!Array.isArray(steps) || steps.length === 0) {
    fail(`Invalid actions payload: ${actionsFile}`)
  }
  return steps
}

async function applyStep(page, step) {
  const frames = Number.isFinite(step.frames) ? Math.max(1, step.frames) : 1
  for (let i = 0; i < frames; i += 1) {
    await page.waitForTimeout(1000 / 60)
  }
}

async function capture(page, name, errors) {
  await page.waitForTimeout(200)
  await page.screenshot({
    path: path.join(outputDir, `${name}.png`),
    fullPage: true,
    timeout: 60000,
  })

  const state = await page.evaluate(() => {
    if (typeof window.render_game_to_text === 'function') {
      return window.render_game_to_text()
    }
    return null
  })

  if (state) {
    fs.writeFileSync(path.join(outputDir, `${name}.json`), state)
  }

  if (errors.length > 0) {
    fs.writeFileSync(
      path.join(outputDir, `${name}-errors.json`),
      JSON.stringify(errors, null, 2),
    )
  }
}

async function main() {
  const steps = loadSteps()
  fs.rmSync(outputDir, { recursive: true, force: true })
  fs.mkdirSync(outputDir, { recursive: true })

  let localServer = null
  let browser = null
  try {
    if (!process.env.UI_E2E_URL) {
      localServer = startLocalServer(internalHost, internalPort)
      await waitForServer(internalHost, internalPort)
    }

    browser = await chromium.launch({
      headless,
      executablePath: resolveChromiumExecutablePath(),
    })
    const page = await browser.newPage({ viewport: { width: 1680, height: 960 } })
    const errors = []

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push({ type: 'console.error', text: msg.text() })
      }
    })
    page.on('pageerror', (err) => {
      errors.push({ type: 'pageerror', text: String(err) })
    })

    await page.goto(url, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(350)

    for (const step of steps) {
      await applyStep(page, step)
    }
    await capture(page, anchorId, errors)
  } finally {
    if (browser) {
      await browser.close()
    }
    if (localServer) {
      localServer.kill('SIGTERM')
    }
  }

  const artifacts = fs.readdirSync(outputDir).sort()
  console.log(`[test:e2e:ui] Artifacts written to ${outputDir}`)
  console.log(`[test:e2e:ui] Files: ${artifacts.join(', ')}`)
}

main().catch((err) => {
  fail(String(err))
})
