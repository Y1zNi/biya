'use strict'
/**
 * 抖音 a_bogus 签名 CLI：从 stdin 读 JSON，向 stdout 输出签名。
 * 输入: { "kind": "detail"|"reply", "query": "<urlencoded params>", "ua": "<user-agent>" }
 */
const fs = require('fs')
const path = require('path')
const vm = require('vm')

function loadDouyinSignSandbox() {
  const douyinPath = path.join(__dirname, 'douyin.js')
  const code = fs.readFileSync(douyinPath, { encoding: 'utf8' })
  const sandbox = { console }
  vm.createContext(sandbox)
  vm.runInContext(code, sandbox, { filename: 'douyin.js' })
  return sandbox
}

function main() {
  const raw = fs.readFileSync(0, 'utf8')
  let input
  try {
    input = JSON.parse(raw.trim() || '{}')
  } catch (err) {
    process.stderr.write(`invalid json: ${err.message}\n`)
    process.exit(3)
  }

  const sandbox = loadDouyinSignSandbox()
  const fnName = input.kind === 'reply' ? 'sign_reply' : 'sign_datail'
  const fn = sandbox[fnName]
  if (typeof fn !== 'function') {
    process.stderr.write(`missing sign function: ${fnName}\n`)
    process.exit(4)
  }

  const result = fn(String(input.query || ''), String(input.ua || ''))
  process.stdout.write(String(result))
}

main()
