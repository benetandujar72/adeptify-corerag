# sample_data — Documents de demostració

> **IMPORTANT: Aquestes dades són SINTÈTIQUES i de demostració.**
> No corresponen a cap persona real ni a cap document oficial de l'Escola Nou Patufet.
> Estan dissenyades únicament per validar la ingesta del backend RAG i l'eval set.

## Propòsit

Aquesta carpeta conté documents d'exemple d'una escola catalana fictícia, en format Markdown,
que el backend del sistema IA Nou Patufet ingestirà i indexarà automàticament a pgvector.

Cada fitxer inclou metadades al capdamunt (títol, versió, data) que el pipeline d'ingesta
(`backend/app/ingest/`) pot aprofitar per als filtres de cerca i la citació de fonts.

## Documents inclosos

| Fitxer | Descripció | Agent principal |
|--------|-----------|----------------|
| `PEC_resum.md` | Projecte Educatiu de Centre (resum) | `documental`, `secretaria` |
| `NOFC_extracte.md` | Normes d'Organització i Funcionament (extracte) | `secretaria` |
| `programacio_matematiques_5e.md` | Programació de matemàtiques, 5è de primària | `tutor_mates` |
| `circular_sortida_3r.md` | Circular a famílies sobre sortida de 3r | `families` |
| `calendari_escolar_2026_2027.md` | Calendari escolar, períodes i festius | `families`, `secretaria` |
| `info_menjador.md` | Informació del servei de menjador | `families` |
| `acta_claustre_exemple.md` | Acta de claustre (exemple) | `documental`, `secretaria` |

## Com s'usa

El backend detecta automàticament tots els fitxers `.md` (i `.pdf`, `.docx`) d'aquesta carpeta.
Per forçar una reingesta:

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Authorization: Bearer <token-direccio>" \
  -H "Content-Type: application/json" \
  -d '{"path": "sample_data/"}'
```

## Substitució per documents reals

En producció, aquests fitxers s'han de substituir pels documents oficials del centre
(NOFC real, PEC real, programacions aprovades, etc.). La ingesta funciona igual;
únicament canvia el contingut dels documents.

Els documents reals **NO s'han de versionar al repositori** si contenen dades sensibles.
Usar `.gitignore` per excloure els fitxers reals i conservar només els sintètics de demostració.
