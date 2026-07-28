import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { chromium } from 'playwright'

const currentDir = fileURLToPath(new URL('.', import.meta.url))
const rootDir = resolve(currentDir, '..', '..')
const frontendDir = resolve(rootDir, 'frontend')
const screenshotsDir = resolve(frontendDir, 'screenshots')
mkdirSync(screenshotsDir, { recursive: true })

function startProcess(command, args, cwd) {
  const proc = spawn(command, args, {
    cwd,
    shell: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: process.env,
  })
  proc.stdout.on('data', (chunk) => process.stdout.write(chunk))
  proc.stderr.on('data', (chunk) => process.stderr.write(chunk))
  return proc
}

async function waitFor(url, label) {
  const started = Date.now()
  while (Date.now() - started < 60000) {
    try {
      const res = await fetch(url)
      if (res.ok) {
        console.log(`${label}: ready`)
        return
      }
    } catch {
      // keep waiting
    }
    await delay(1000)
  }
  throw new Error(`${label} did not become ready in time`)
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(`FAIL: ${message}`)
  }
  console.log(`PASS: ${message}`)
}

async function logPanelState(page, label) {
  const html = await page.locator('[data-testid="evidence-panel"]').evaluate((el) => el.outerHTML)
  console.log(`${label} evidence panel HTML:`)
  console.log(html)
}

async function captureFailureArtifacts(page, name) {
  const path = resolve(screenshotsDir, name)
  await page.screenshot({ path, fullPage: true })
  console.log(`Saved failure screenshot: ${path}`)
  await logPanelState(page, 'Failure snapshot')
}

async function main() {
  const backend = startProcess('python', ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8020'], rootDir)
  const frontend = startProcess('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173'], frontendDir)

  const cleanup = async () => {
    backend.kill()
    frontend.kill()
    await delay(1500)
  }

  try {
    await waitFor('http://127.0.0.1:8020/api/health', 'backend')
    await waitFor('http://127.0.0.1:5173', 'frontend')

    const browser = await chromium.launch({ headless: true })
    const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
    const page = await context.newPage()
    const apiCalls = []
    page.on('request', (request) => {
      if (request.url().includes('/api/ask')) {
        apiCalls.push(request.url())
      }
    })

    const openFrontend = async () => {
      await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle' })
      await assert(page.getByRole('heading', { name: 'SFCollab Research Reply Agent' }).isVisible(), 'frontend shell renders')
    }

    await openFrontend()

    // Test case 1
    await page.getByLabel('Question input').fill('How do I update my profile picture?')
    const askResponse1 = page.waitForResponse((response) => response.url().includes('/api/ask') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Ask' }).click()
    await askResponse1
    await page.getByText('Retrieved Evidence').waitFor({ state: 'visible' })
    await page.getByText('Draft Reply').waitFor({ state: 'visible' })
    await page.screenshot({ path: resolve(screenshotsDir, 'test1_results.png'), fullPage: true })

    const snippetCards = page.locator('.snippet')
    try {
      await assert((await snippetCards.count()) >= 1, 'good match returns at least one snippet')
      await assert(await page.getByText(/Score: 0\.\d{3}/).first().isVisible(), 'good match shows visible score text')

      const draftText1 = (await page.locator('[data-testid="draft-panel"] .draft-text').innerText()).trim()
      await assert(draftText1.length > 20, 'good match draft is longer than 20 characters')
      await assert(!/null|undefined|NaN/i.test(draftText1), 'good match draft contains no null/undefined/NaN placeholders')
    } catch (error) {
      await captureFailureArtifacts(page, 'test1_failure.png')
      throw error
    }

    await page.getByRole('button', { name: 'Discard' }).click()
    await page.screenshot({ path: resolve(screenshotsDir, 'test1_after_discard.png'), fullPage: true })
    await assert((await page.getByLabel('Question input').inputValue()) === '', 'discard clears the question input')
    await assert((await page.locator('.snippet').count()) === 0, 'discard removes snippet cards from the UI')
    await assert((await page.locator('[data-testid="draft-panel"] .draft-text').count()) === 0, 'discard removes draft text from the UI')

    // Test case 2
    await page.getByLabel('Question input').fill("What's the weather like today?")
    const askResponse2 = page.waitForResponse((response) => response.url().includes('/api/ask') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Ask' }).click()
    await askResponse2
    await page.screenshot({ path: resolve(screenshotsDir, 'test2_results.png'), fullPage: true })
    await assert(await page.getByText('No relevant help content found for this question.').isVisible(), 'no-match evidence message is shown')
    await assert(await page.getByText(/I don'?t have enough information in the help content to answer this confidently\./).isVisible(), 'no-match refusal text is shown')
    await assert(await page.locator('[data-testid="draft-panel"]').evaluate((el) => el.classList.contains('ungrounded')), 'no-match draft panel is marked ungrounded')

    // Test case 3
    await page.getByRole('button', { name: 'Discard' }).click()
    await page.getByLabel('Question input').fill('How do I update my profile picture?')
    const askResponse3 = page.waitForResponse((response) => response.url().includes('/api/ask') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Ask' }).click()
    await askResponse3
    const priorApiCalls = apiCalls.length
    await page.getByRole('button', { name: 'Approve' }).click()
    await page.screenshot({ path: resolve(screenshotsDir, 'test3_approved.png'), fullPage: true })
    await assert(await page.getByText('Approved (not sent — no delivery destination in this task)').isVisible(), 'approval confirmation appears')
    await assert(apiCalls.length === priorApiCalls, 'approve flow does not trigger any extra network request')

    console.log('All assertions passed.')
    await browser.close()
  } catch (error) {
    if (typeof page !== 'undefined') {
      try {
        await captureFailureArtifacts(page, 'failure.png')
      } catch {
        // best effort only
      }
    }
    throw error
  } finally {
    await cleanup()
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
