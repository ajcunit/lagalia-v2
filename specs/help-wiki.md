# Centre d'ajuda integrat (Estat: implementada)

## Context i objectiu

Petició de l'Esteve (2026-08-19), abans del desplegament de test: una
secció d'ajuda tipus **wiki de funcionament**, integrada amb el xat, i
que **no mostri la informació de configuració als qui no són admins**.

## Comportament

- **Contingut**: articles en Markdown, estàtics i versionats amb el codi
  (`app/modules/help/articles.py`) — un canvi de funcionament ha de tocar
  l'article corresponent, com una spec més. Cada article té `audience`:
  `all` o `admin`.
- **API**: `GET /help` (llista visible segons rol) i `GET /help/{slug}`
  (cos). Els articles `admin` només per al rol admin; demanar-ne un sense
  ser-ho és **404** (no es filtra ni l'existència).
- **Pantalla** `/help` («Ajuda», al peu del sidebar **a sobre de
  Configuració**, visible per a tothom): índex amb cerca per títol +
  lectura Markdown; els articles d'administració van marcats. Targeta
  «Pregunta-ho al xat» si l'usuari té accés al xat i el mòdul és actiu.
- **Integració amb el xat**: eina `help_articles` de l'assistent general
  (cerca per paraules clau, retorna fins a 3 articles) perquè respongui
  «com funciona X?». L'eina serveix **només audiència general**: els
  articles d'administració mai passen pel xat (hi accedeixen rols amb
  permís d'anàlisi que no són admins).

## Canvis d'API

`GET /help`, `GET /help/{slug}` (tag `help`; sessió). Client TS regenerat.

## Seguretat

- Filtre d'audiència al servidor (rol real de la sessió), mai al client.
- El wiki no conté secrets ni dades: només funcionament.

## Fora d'abast

- Edició del wiki des de la UI (el contingut viu al repositori).
- Cerca de text complet al cos (la cerca de pantalla és per títol; el xat
  sí que cerca al cos).

## Criteris d'acceptació

- [x] Un empleat veu el manual d'usuari; els articles d'administració ni
  es llisten ni es poden obrir (404).
- [x] Un admin ho veu tot; el xat respon preguntes d'ús amb el wiki.
- [x] Entrada «Ajuda» al sidebar sobre Configuració; bateries verdes.
