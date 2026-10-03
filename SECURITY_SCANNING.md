# Controles ejecutables de seguridad

CI analiza el árbol versionado y la historia alcanzable sin leer `.env` local ignorado. El informe contiene rutas, reglas y huellas, nunca valores. El control de dependencias consulta OSV con nombres/versiones públicos del lock Linux CPU; no sube código ni datos.

Instalar `pre-commit` en un entorno de desarrollo y ejecutar `pre-commit install` activa el mismo control de árbol antes de cada commit. El hook es adicional: el control obligatorio está en CI. Proteger la rama para exigir ambos trabajos.

Los tests y ejemplos no tienen excepciones por ruta ni por contener «dummy». Una excepción requiere revisión humana de la coincidencia exacta, servicio identificado y ticket. El auditor permite `--permet-fp FP:TIPUS:RUTA`; datos identificables requieren además `--permet-pii FP:TIPUS:RUTA=TIQUET`. No introducir excepciones de huella sin alcance de regla/ruta ni silenciar una credencial real. Tras revisar, sustituir fixtures por valores sintéticos y rotar credenciales operativas en su servicio antes de considerar un incidente cerrado.

Un fallo de red, inventario incompleto, archivo excesivo o historia inaccesible impide declarar el análisis limpio. La historia y blobs huérfanos anteriores se revisan de forma privada antes de publicar; CI no sustituye ese triaje. Conservar una copia cifrada recuperable y comprobar recuperación antes de cualquier saneamiento de historia autorizado.

Para regenerar el lock usar `uv pip compile` con Python 3.11, plataforma Linux, `--torch-backend cpu --generate-hashes` y todos los requisitos de despliegue (en Suite también NER y su modelo). Validar primero modelos y grafos en un entorno aislado, `pip check` y el auditor; después reconstruir la imagen y volver a analizar sus paquetes de sistema.
