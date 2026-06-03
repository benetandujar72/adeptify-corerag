import { createContext } from 'react'
import { IDIOMES_ADMESOS, type Idioma } from './catalogs'

const STORAGE_KEY = 'app.idioma'

export interface I18nContextValue {
  idioma: Idioma
  setIdioma: (i: Idioma) => void
  t: (clau: string) => string
}

export const I18nContext = createContext<I18nContextValue | null>(null)

export function llegeixIdiomaInicial(): Idioma {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v && (IDIOMES_ADMESOS as string[]).includes(v)) return v as Idioma
  } catch {
    /* localStorage no disponible (SSR/test) */
  }
  return 'ca'
}

export function desaIdioma(i: Idioma) {
  try {
    localStorage.setItem(STORAGE_KEY, i)
  } catch {
    /* localStorage no disponible */
  }
}
