// ─── Branding per institució (multi-tenant) ──────────────────────────────────
// Aplica el tema d'una institució sobreescrivint variables CSS que Tailwind
// llegeix per als colors de marca (navy = primari, terra = secundari/accent).
// Els valors per defecte coincideixen amb `:root` a index.css i amb
// tailwind.config.js, de manera que sense branding l'aspecte és l'original.

import type { InstitucioBranding } from '../types'

// Canals "r g b" per defecte (han de coincidir amb index.css i tailwind.config.js).
const DEFAULT_NAVY = '11 37 69' //   #0B2545
const DEFAULT_TERRA = '201 123 78' // #C97B4E

/** Converteix un color hex (#RRGGBB o #RGB) als canals "r g b". null si no és vàlid. */
export function hexToRgbChannels(hex?: string | null): string | null {
  if (!hex) return null
  let h = hex.trim().replace(/^#/, '')
  if (h.length === 3) {
    h = h
      .split('')
      .map(c => c + c)
      .join('')
  }
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `${r} ${g} ${b}`
}

/**
 * Aplica el branding d'una institució: colors de marca (CSS vars) + títol de la
 * pestanya. Si un color no és vàlid o falta, recau al valor per defecte.
 */
export function applyBranding(branding?: InstitucioBranding | null, nom?: string): void {
  const root = document.documentElement
  const primari = hexToRgbChannels(branding?.color_primari) ?? DEFAULT_NAVY
  const secundari = hexToRgbChannels(branding?.color_secundari) ?? DEFAULT_TERRA
  root.style.setProperty('--brand-navy-rgb', primari)
  root.style.setProperty('--brand-terra-rgb', secundari)
  if (nom) document.title = `${nom} · IA Assistent`
}

/** Restaura el tema per defecte (en tancar sessió). */
export function resetBranding(): void {
  const root = document.documentElement
  root.style.setProperty('--brand-navy-rgb', DEFAULT_NAVY)
  root.style.setProperty('--brand-terra-rgb', DEFAULT_TERRA)
  document.title = 'Nou Patufet · IA Assistent'
}

const STOP_WORDS = new Set([
  'escola', 'col·legi', 'collegi', 'colegio', 'institut', 'instituto', 'ceip',
  'centre', 'centro', 'de', 'del', 'la', 'el', 'els', 'les', 'i', 'd',
])

/**
 * Inicials per al badge del logo. Prioritat: `logo_text` → inicials del nom
 * (ignorant paraules genèriques com "Escola"). Màxim 2 lletres.
 */
export function logoInicials(branding?: InstitucioBranding | null, nom?: string): string {
  if (branding?.logo_text) return branding.logo_text.slice(0, 3)
  const base = (nom ?? '').trim()
  if (!base) return 'NP'
  const paraules = base
    .split(/[\s._-]+/)
    .filter(w => w.length > 0 && !STOP_WORDS.has(w.toLowerCase()))
  const font = paraules.length > 0 ? paraules : base.split(/\s+/)
  return (
    font
      .slice(0, 2)
      .map(w => w[0]?.toUpperCase() ?? '')
      .join('') || 'NP'
  )
}
