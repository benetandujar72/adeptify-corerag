/** A silent or disconnected server must not leave private data on screen. */
export async function ambTerminiSortida<T>(
  accio: (signal: AbortSignal) => Promise<T>,
  terminiMs = 5000,
): Promise<T> {
  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout> | undefined
  const termini = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      controller.abort()
      reject(new Error('El servidor no ha confirmat el tancament de sessió.'))
    }, terminiMs)
  })
  try { return await Promise.race([accio(controller.signal), termini]) }
  finally { clearTimeout(timer) }
}
