# Identitat de xarxa darrere d'un proxy

L'arrencada Docker i el comandament local desactiven la reescriptura de capçaleres
d'Uvicorn amb `--no-proxy-headers`. Cal conservar-ho en qualsevol servei, process
manager o comandament personalitzat: el guardià necessita la IP real del socket.

Per servir l'API a través de nginx, configura `PROXY_DE_CONFIANCA=true` i
`PROXY_TRUSTED_CIDRS` amb les IP/CIDR dels proxies reals: el peer que connecta al
backend i els intermediaris (p. ex. cloudflared). El valor buit no confia en cap
proxy. Prefereix adreces estables /32 o /128 o una xarxa exclusiva i protegida de
proxies. No autoritzis tot un bridge Docker compartit, la LAN d'usuaris ni 0.0.0.0/0.
Una IP de proxy autoritzada pot aportar identitats a X-Forwarded-For.

Nginx conserva la cadena rebuda i afegeix el peer real a la dreta. El guardià
accepta aquesta cadena només quan el socket pertany a un proxy explícit, descarta
els intermediaris de confiança des de la dreta i pren el primer origen restant.
Un prefix aportat pel navegador no determina la identitat. Una cadena malformada,
buida o composta només per proxies, o confiança absent, es tracta com a origen
remot/desconegut. Amb proxy desactivat però XFF present també es tanca l'accés LAN:
la IP privada del bridge no identifica l'usuari que navega.

Configura `XARXA_LOCAL_CIDRS` (buit per defecte) amb les subxarxes reals d'usuaris LAN/VPN i revisa la
política d'IP de cada institució. No incloguis els bridges interns dels proxies en
aquesta llista. Si la política limita els rols no administradors a la xarxa del
centre, aquests necessiten una identitat LAN/VPN verificada. Una visita per túnel
des d'Internet continua sent remota; el túnel no acredita pertinença a la LAN.
Un intermediari no declarat tampoc rep privilegis pel simple fet de tenir una IP
privada. Les dues llistes han de ser explícites: proxies de confiança i xarxes
d'usuaris permesos. Elimina els rangs privats amplis de configuracions antigues.

Abans d'aplicar aquests canvis: confirma totes les IP de peer i salts reals,
configura la confiança, comprova accés docent per LAN/VPN i denegació externa i
mantén un accés d'administració per recuperar una configuració equivocada. Si un
proxy canvia d'IP, revisa la confiança abans de recrear-lo. L'auditoria modifica
fitxers revisables; no ha canviat .env reals ni reiniciat producció.
