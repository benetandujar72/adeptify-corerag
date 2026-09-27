#!/usr/bin/env node
// Genera public/THIRD_PARTY_NOTICES.txt a partir de l'arbre de dependències de
// PRODUCCIÓ (les que acaben dins el bundle distribuït). Es corre automàticament
// abans de `npm run build` (script `prebuild`) perquè el fitxer no es desincronitzi
// mai de les dependències reals.
//
// MIT i ISC exigeixen que l'avís de copyright i l'avís de permís es distribueixin
// amb el programari. Aquest fitxer és el "fitxer complementari" on es compleix
// aquesta obligació per a totes les llibreries de codi obert incloses al frontend.

import { execSync } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = join(__dirname, '..')
const OUT_PATH = join(ROOT, 'public', 'THIRD_PARTY_NOTICES.txt')

const LICENSE_FILENAMES = [
  'LICENSE', 'LICENSE.md', 'LICENSE.txt', 'LICENSE-MIT',
  'License', 'license', 'LICENCE', 'LICENCE.md',
]

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'))
}

function findLicenseText(pkgDir) {
  for (const name of LICENSE_FILENAMES) {
    const p = join(pkgDir, name)
    if (existsSync(p)) return readFileSync(p, 'utf8').trim()
  }
  return null
}

/** Recorre l'arbre `npm ls --omit=dev --all --json` i retorna un mapa únic name -> {version, path}. */
function collectProdDependencies() {
  const raw = execSync(
    'npm ls --omit=dev --all --json --long',
    { cwd: ROOT, encoding: 'utf8', maxBuffer: 1024 * 1024 * 20 },
  )
  const tree = JSON.parse(raw)
  const found = new Map() // key: name@version -> { name, version, path }

  function walk(deps) {
    if (!deps) return
    for (const [name, info] of Object.entries(deps)) {
      if (info.path) {
        const key = `${name}@${info.version}`
        if (!found.has(key)) found.set(key, { name, version: info.version, path: info.path })
      }
      if (info.dependencies) walk(info.dependencies)
    }
  }
  walk(tree.dependencies)
  return [...found.values()].sort((a, b) => a.name.localeCompare(b.name))
}

function build() {
  const ownPkg = readJson(join(ROOT, 'package.json'))
  const packages = collectProdDependencies()
  const sections = []
  const missing = []

  for (const pkg of packages) {
    const pkgJson = readJson(join(pkg.path, 'package.json'))
    const licenseId = pkgJson.license ?? (Array.isArray(pkgJson.licenses) ? pkgJson.licenses.map(l => l.type).join(' OR ') : 'DESCONEGUDA')
    const text = findLicenseText(pkg.path)
    if (!text) missing.push(`${pkg.name}@${pkg.version} (${licenseId})`)
    sections.push(
      [
        '─'.repeat(78),
        `${pkg.name}@${pkg.version} — llicència ${licenseId}`,
        '─'.repeat(78),
        text ?? `(Cap fitxer LICENSE trobat al paquet. Llicència declarada: ${licenseId}.)`,
      ].join('\n'),
    )
  }

  const header = [
    `AVISOS DE TERCERS — ${ownPkg.name}`,
    '',
    '(Vegeu el fitxer LICENSE a l\'arrel del repositori per als termes propis',
    'd\'aquest programa.) Aquest build incorpora, sense modificar-ne el codi font,',
    'les llibreries de codi obert següents. Es reprodueixen aquí els avisos de',
    'copyright i les llicències de permís tal com les exigeixen les seves',
    'llicències MIT/ISC per a qualsevol còpia distribuïda d\'aquest programari.',
    '',
    `Generat automàticament el ${new Date().toISOString()} per`,
    'scripts/generate-third-party-notices.mjs — no editar a mà.',
    '',
  ].join('\n')

  // BOM: el servidor estàtic no sempre envia `charset=utf-8` per a .txt, i sense
  // pista el navegador pot interpretar els accents com Latin-1. El BOM força UTF-8.
  writeFileSync(OUT_PATH, '﻿' + header + '\n' + sections.join('\n\n') + '\n', 'utf8')

  console.log(`[third-party-notices] ${packages.length} paquets documentats -> ${OUT_PATH}`)
  if (missing.length) {
    console.warn('[third-party-notices] AVÍS: cap fitxer LICENSE trobat per a:')
    for (const m of missing) console.warn(`  - ${m}`)
    console.warn('Revisa\'ls manualment abans de publicar.')
  }
}

mkdirSync(join(ROOT, 'public'), { recursive: true })
build()
