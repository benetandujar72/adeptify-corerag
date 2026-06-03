import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { tradueix, type Idioma } from './catalogs'
import { desaIdioma, I18nContext, llegeixIdiomaInicial, type I18nContextValue } from './context'

export function I18nProvider({ children }: { children: ReactNode }) {
  const [idioma, setIdiomaState] = useState<Idioma>(llegeixIdiomaInicial)

  const setIdioma = useCallback((i: Idioma) => {
    setIdiomaState(i)
    desaIdioma(i)
  }, [])

  useEffect(() => {
    // Marca l'atribut lang del document per a accessibilitat (lectors de pantalla).
    document.documentElement.lang = idioma
  }, [idioma])

  const value = useMemo<I18nContextValue>(() => ({
    idioma,
    setIdioma,
    t: (clau: string) => tradueix(clau, idioma),
  }), [idioma, setIdioma])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}
