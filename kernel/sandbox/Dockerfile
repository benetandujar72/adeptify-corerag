# Imatge del SANDBOX d'execució (K4.1/K4.5). Mínima i SENSE shell de host.
FROM python:3.12-slim

# Usuari no-root.
RUN useradd --uid 10003 --no-create-home --shell /usr/sbin/nologin sandbox

# K4.5: ELIMINA qualsevol shell de la imatge (aquesta és l'última capa que pot usar
# /bin/sh; després ja no hi ha cap shell). Així `subprocess(["sh"/"bash"])` → FileNotFoundError.
RUN rm -f /bin/sh /bin/bash /bin/dash /bin/rbash /usr/bin/bash /usr/bin/dash /usr/bin/sh /usr/bin/rbash

USER sandbox
# Entrypoint = python (exec form, sense shell). El payload entra com a `-c "<codi>"`.
ENTRYPOINT ["python"]
CMD ["-c", "print('sandbox ready')"]
