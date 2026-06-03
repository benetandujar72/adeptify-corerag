// ─── Pàgina Documents: gestió i incorporació de documents ────────────────────
// Llista els documents indexats i permet pujar-ne de nous (drag&drop o selector).
// La ingesta crida POST /api/ingest (multipart) i refresca GET /api/documents.

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  UploadCloud,
  FileText,
  Loader2,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Database,
  Trash2,
} from 'lucide-react'
import { deleteDocument, fetchDocuments, uploadDocument } from '../api/client'
import type { DocumentEstat } from '../types'

const TIPUS_COLOR: Record<string, string> = {
  pdf: 'bg-terra',
  docx: 'bg-navy',
  xlsx: 'bg-green',
  md: 'bg-sage',
  html: 'bg-cherry',
  image: 'bg-[#7C3AED]',
}

interface Estat {
  tipus: 'ok' | 'error' | 'info'
  text: string
}

export function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentEstat[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [estat, setEstat] = useState<Estat | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const loadDocs = useCallback(async () => {
    setLoading(true)
    try {
      setDocs(await fetchDocuments())
    } catch (e) {
      setEstat({ tipus: 'error', text: (e as Error).message })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadDocs()
  }, [loadDocs])

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const llista = Array.from(files)
      if (llista.length === 0) return
      setUploading(true)
      setEstat({ tipus: 'info', text: `Pujant i indexant ${llista.length} fitxer(s)…` })
      let ok = 0
      const errors: string[] = []
      for (const file of llista) {
        try {
          await uploadDocument(file)
          ok += 1
        } catch (e) {
          errors.push(`${file.name}: ${(e as Error).message}`)
        }
      }
      setUploading(false)
      if (errors.length === 0) {
        setEstat({ tipus: 'ok', text: `${ok} fitxer(s) indexat(s) correctament.` })
      } else {
        setEstat({
          tipus: 'error',
          text: `${ok} indexat(s), ${errors.length} amb error. ${errors.join(' · ')}`,
        })
      }
      await loadDocs()
    },
    [loadDocs],
  )

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files?.length) void handleFiles(e.dataTransfer.files)
  }

  async function handleDelete(doc_id: string, filename: string) {
    if (!window.confirm(`Vols esborrar "${filename}" de la biblioteca? No es pot desfer.`)) return
    setDeleting(doc_id)
    try {
      await deleteDocument(doc_id)
      setEstat({ tipus: 'ok', text: `"${filename}" esborrat de la biblioteca.` })
      await loadDocs()
    } catch (e) {
      setEstat({ tipus: 'error', text: (e as Error).message })
    } finally {
      setDeleting(null)
    }
  }

  const totalFragments = docs.reduce((s, d) => s + d.fragments, 0)

  return (
    <div className="flex-1 overflow-y-auto bg-fons">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Capçalera */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-navy">Documents del centre</h1>
            <p className="text-sm text-muted mt-1">
              Incorpora documents al coneixement de la IA. Tot el processament és local.
            </p>
          </div>
          <button
            onClick={() => void loadDocs()}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-white text-sm text-dark hover:bg-crema transition-colors"
          >
            <RefreshCw size={14} /> Actualitza
          </button>
        </div>

        {/* Zona de pujada */}
        <div
          onDragOver={e => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center transition-colors ${
            dragOver ? 'border-terra bg-terra/5' : 'border-border bg-white hover:border-sage'
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.md,.html,.htm,.txt,.png,.jpg,.jpeg,.tiff,.tif,.bmp"
            className="hidden"
            onChange={e => {
              if (e.target.files) void handleFiles(e.target.files)
              e.target.value = ''
            }}
          />
          <div className="flex flex-col items-center gap-2">
            {uploading ? (
              <Loader2 size={36} className="text-terra animate-spin" />
            ) : (
              <UploadCloud size={36} className="text-sage" />
            )}
            <p className="text-sm font-medium text-dark">
              {uploading
                ? 'Indexant… (embedding + chunking en local)'
                : 'Arrossega fitxers aquí o fes clic per seleccionar-los'}
            </p>
            <p className="text-xs text-muted">
              PDF · DOCX · Markdown · HTML · TXT · Imatges (OCR). La ingesta classifica sensibilitat i sortida IA.
            </p>
          </div>
        </div>

        {/* Missatge d'estat */}
        {estat && (
          <div
            className={`mt-4 flex items-start gap-2 px-4 py-3 rounded-lg text-sm ${
              estat.tipus === 'ok'
                ? 'bg-green/10 text-green border border-green/30'
                : estat.tipus === 'error'
                  ? 'bg-red-50 text-red-600 border border-red-200'
                  : 'bg-userbubble text-navy border border-navy/10'
            }`}
          >
            {estat.tipus === 'ok' ? (
              <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
            ) : estat.tipus === 'error' ? (
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
            ) : (
              <Loader2 size={16} className="mt-0.5 shrink-0 animate-spin" />
            )}
            <span>{estat.text}</span>
          </div>
        )}

        {/* Resum d'indexació */}
        <div className="mt-6 flex items-center gap-4 text-sm text-muted">
          <span className="flex items-center gap-2">
            <Database size={15} className="text-sage" />
            <strong className="text-navy">{docs.length}</strong> documents
          </span>
          <span>
            <strong className="text-navy">{totalFragments}</strong> fragments (chunks) a pgvector
          </span>
        </div>

        {/* Taula de documents */}
        <div className="mt-3 bg-white rounded-xl border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-crema text-muted text-left">
                <th className="px-4 py-2.5 font-semibold">Fitxer</th>
                <th className="px-4 py-2.5 font-semibold w-20">Tipus</th>
                <th className="px-4 py-2.5 font-semibold w-24 text-right">Fragments</th>
                <th className="px-4 py-2.5 font-semibold w-28">Verificat</th>
                <th className="px-4 py-2.5 font-semibold w-28">Origen</th>
                <th className="px-4 py-2.5 font-semibold w-28">Seguretat</th>
                <th className="px-4 py-2.5 font-semibold w-24">Estat</th>
                <th className="px-4 py-2.5 font-semibold w-12"></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-muted">
                    <Loader2 size={20} className="animate-spin inline mr-2" /> Carregant…
                  </td>
                </tr>
              ) : docs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-muted">
                    Encara no hi ha documents. Puja'n el primer a dalt.
                  </td>
                </tr>
              ) : (
                docs.map(d => (
                  <tr key={d.doc_id} className="border-t border-border hover:bg-crema/50">
                    <td className="px-4 py-2.5">
                      <span className="flex items-center gap-2 text-dark">
                        <FileText size={15} className="text-muted shrink-0" />
                        {d.filename}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-white text-xs font-bold ${
                          TIPUS_COLOR[d.tipus] ?? 'bg-muted'
                        }`}
                      >
                        {d.tipus.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-dark">{d.fragments}</td>
                    <td className="px-4 py-2.5 text-muted text-xs">{d.verificat_el ?? '—'}</td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex rounded border border-border px-2 py-0.5 text-xs text-navy bg-white">
                        {d.origen}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold ${
                          d.sensibilitat === 'sensible'
                            ? 'bg-red-50 text-red-600 border border-red-200'
                            : d.exportable_ia
                              ? 'bg-green/10 text-green border border-green/30'
                              : 'bg-crema text-muted border border-border'
                        }`}
                        title={d.exportable_ia ? 'Pot usar-se com a context no sensible' : 'No surt a IA externa'}
                      >
                        {d.sensibilitat}{d.exportable_ia ? ' · IA externa OK' : ''}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex items-center gap-1 text-xs text-green">
                        <CheckCircle2 size={13} /> {d.estat}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        onClick={() => void handleDelete(d.doc_id, d.filename)}
                        disabled={deleting === d.doc_id}
                        title="Esborrar de la biblioteca"
                        className="text-muted hover:text-red-600 transition-colors disabled:opacity-40"
                      >
                        {deleting === d.doc_id ? (
                          <Loader2 size={15} className="animate-spin" />
                        ) : (
                          <Trash2 size={15} />
                        )}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
