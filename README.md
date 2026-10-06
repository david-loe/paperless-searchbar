# Paperless Searchbar

Eine deutschsprachige, rein lesende Web-App für Paperless-ngx v3. Suche nach **interner Dokument-ID, Custom Fields, Speicherpfad, Korrespondent und Dokumenttyp**, öffne die PDF-Vorschau oder lade ein Dokument herunter. Bearbeitet wird über einen Link direkt in Paperless.

Die App verwendet **Python 3.14 / FastAPI** und **Vue 3 / TypeScript / Vite / Tailwind CSS**. Ein Container liefert Frontend und API aus. SQLite speichert Benutzer, Freigaben und Sitzungen in einem Volume; Dokumente bleiben in Paperless.

## Start mit Docker Compose

```sh
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Den erzeugten Schlüssel als `SECRET_KEY` in `.env` eintragen und Paperless-Adressen sowie Token ergänzen. Die interne Adresse muss **aus dem Container** erreichbar sein; `localhost` bezeichnet dort den Searchbar-Container. Für Paperless in einem anderen Compose-Projekt beide Dienste über ein gemeinsames Docker-Netzwerk verbinden oder eine erreichbare Instanzadresse verwenden.

Zum lokalen Bauen und Starten:

```sh
docker compose up -d --build
docker compose exec searchbar python -m searchbar.cli admin-code
```

Der zweite Befehl legt den lokalen Administrator an und zeigt einen zufälligen **Admin-Zugangscode einmalig** an. Den Code sicher aufbewahren: Er gilt bis zum Ersetzen. Erneutes Ausführen erzeugt einen neuen Code und meldet alle bisherigen Sitzungen dieses Administrators ab. In der Datenbank wird ausschließlich ein HMAC-Hash gespeichert.

Die App ist anschließend auf <http://localhost:8000> erreichbar. Den Admin-Code auf der Loginseite in dasselbe Feld **Zugangscode** wie einen Gastcode eingeben. Es gibt keine separate Anmeldung mit Benutzername und Passwort.

Mit `--name <kennung>` kann ein anderer lokaler Administrator gezielt angelegt oder dessen Code ersetzt werden. Ohne Parameter lautet die interne Kennung `admin`; sie wird bei der Anmeldung nicht benötigt. Gesperrte Konten bleiben auch nach einer Code-Erneuerung gesperrt und müssen durch einen anderen Administrator in der Benutzerverwaltung freigeschaltet werden.

Nach der ersten Veröffentlichung des Images kann der Build entfallen:

```sh
docker compose pull
docker compose up -d --no-build
```

`SEARCHBAR_TAG` wählt den Image-Tag; Standard ist `latest`. Für den ersten Entwicklungsstand vor dem ersten stabilen Release `SEARCHBAR_TAG=edge` verwenden. Images werden erst durch einen erfolgreichen Workflow im GitHub-Repository veröffentlicht.

## Paperless-Zugang einrichten

In Paperless einen dedizierten technischen Benutzer erstellen und einen API-Token für diesen Benutzer erzeugen. Er benötigt:

- Leserechte auf die Dokumente, die die App anbieten soll, einschließlich der jeweiligen Objektfreigaben.
- Leserechte auf Korrespondenten, Speicherpfade, Dokumenttypen und Custom Fields, die zur Suche und zur Prüfung von Profilen benötigt werden.
- Für OIDC zusätzlich **Benutzer ansehen** (`auth.view_user`), damit Konten per E-Mail zugeordnet und vor Zugriffen geprüft werden können. Gruppenleserechte sind nicht nötig.
- Keine Superuser-, Änderungs-, Upload- oder Löschrechte.

Gastzugänge und lokale Administratoren können höchstens die Dokumente lesen, die dieser technische Benutzer lesen darf. OIDC-Benutzer benötigen ein eigenes Paperless-Konto und lesen Dokumente mit dessen Rechten; der technische Token begrenzt ihre Dokumentauswahl nicht. Der Bearbeitungslink überträgt keine Zugangsdaten; in Paperless gelten dessen eigene Anmeldung und Berechtigungen.

Die App spricht ausschließlich lesende Paperless-Endpunkte an. Vorschauen und Downloads werden nach Freigabeprüfung über das Backend gestreamt. Der Paperless-Token wird nicht an den Browser weitergegeben.

## Konfiguration

| Variable | Bedeutung |
| --- | --- |
| `APP_URL` | Öffentliche Origin der App, z. B. `https://suche.example.com`; ohne Unterpfad. Relevant für OIDC, Cookies und CSRF. |
| `PAPERLESS_URL` | Interne Basisadresse von Paperless, ohne `/api/`. |
| `PAPERLESS_HTTP_REMOTE_USER_HEADER_NAME` | Derselbe Django-Headername wie in Paperless, Standard `HTTP_REMOTE_USER`. Beispiel: `HTTP_X_AUTH_USER` sendet `X-Auth-User`. |
| `PAPERLESS_PUBLIC_URL` | Öffentliche Basisadresse von Paperless für Bearbeitungslinks. |
| `PAPERLESS_TOKEN` | API-Token des technischen Lesebenutzers. |
| `SECRET_KEY` | Zufälliger Schlüssel mit mindestens 32 Zeichen. Eine Änderung macht vorhandene Sitzungen, Gastcodes und lokale Admin-Codes ungültig. |
| `DATABASE_URL` | Standard: `sqlite:////data/searchbar.db`. Diese Version unterstützt SQLite. |
| `OIDC_ISSUER` | Optional: exakter Issuer aus dem Discovery-Dokument des Providers. |
| `OIDC_CLIENT_ID` | Client-ID; gemeinsam mit dem Issuer angeben. |
| `OIDC_CLIENT_SECRET` | Client-Secret des vertraulichen OIDC-Clients. |
| `FORWARDED_ALLOW_IPS` | Vertrauenswürdige Proxy-IP-Adressen oder -Netze für Uvicorn. Standard: `127.0.0.1`. |
| `STATIC_DIR` | Pfad der gebauten Vue-Oberfläche; im Image `/app/frontend/dist`. |

`SECRET_KEY_FILE`, `PAPERLESS_TOKEN_FILE` und `OIDC_CLIENT_SECRET_FILE` können auf eingebundene Secret-Dateien verweisen. Die Datei hat Vorrang vor dem entsprechenden direkten Wert. Diese Pfade müssen im Container existieren; Docker Secrets über die eigene Compose-Konfiguration einbinden.

Nur eine App-Instanz mit einem Worker betreiben. `/data` muss für UID/GID `10001:10001` schreibbar sein; das mitgelieferte benannte Volume wird beim ersten Start passend initialisiert. Ein Bind-Mount benötigt passende Eigentümerrechte. Die Schemainitialisierung läuft vor jedem Start; bei einem Fehler startet die App nicht.

### HTTPS und Traefik

Der Container spricht HTTP. Für externes HTTPS `APP_URL=https://…` setzen; dadurch erhalten die Sitzungscookies das `Secure`-Attribut. Traefik übernimmt TLS. `FORWARDED_ALLOW_IPS` auf die tatsächliche Proxy-IP beziehungsweise das dedizierte Proxy-Netz beschränken.

Das optionale Overlay setzt ein bestehendes Traefik-Netzwerk und einen `websecure`-Entrypoint voraus. Zertifikate beziehungsweise ein Certificate Resolver werden in Traefik eingerichtet.

In `.env` zusätzlich konfigurieren:

```dotenv
APP_URL=https://suche.example.com
SEARCHBAR_HOST=suche.example.com
TRAEFIK_NETWORK=proxy
# Beispiel: durch das tatsächliche dedizierte Proxy-Netz ersetzen.
FORWARDED_ALLOW_IPS=172.30.0.0/24
```

```sh
docker compose -f compose.yaml -f compose.traefik.yaml up -d
```

Das Overlay entfernt die Host-Portfreigabe. Es benötigt Docker Compose mit Unterstützung für `!reset`. Die App muss Paperless und den OIDC-Provider aus diesem Netzwerk erreichen können. Betrieb unter einem URL-Unterpfad wird nicht unterstützt.

## OIDC

Beim Identity Provider einen Web-Client für Authorization Code Flow mit PKCE anlegen. Exakt folgende Redirect-URI erlauben:

```text
https://suche.example.com/api/auth/oidc/callback
```

Für die lokale Entwicklung entsprechend `http://localhost:5173/api/auth/oidc/callback` verwenden. Issuer, Client-ID und Client-Secret in `.env` setzen. Die App verwendet Discovery und fordert `openid profile email` an. Der Provider muss GET-Callbacks mit `response_mode=query` unterstützen.

Die lokale Identität wird durch **Issuer und Subject** bestimmt. Zur Zuordnung zum Paperless-Konto muss der Provider `email` und den booleschen Claim `email_verified: true` liefern. Die bestätigte Adresse wird ohne äußere Leerzeichen und ohne Beachtung der Großschreibung mit den Paperless-Adressen verglichen. Es muss genau ein Konto passen; fehlende, doppelte oder deaktivierte Konten erhalten keinen Dokumentzugriff. Nach einer Korrektur erneut anmelden.

OIDC-Benutzer erhalten automatisch die Dokumentrechte ihres Paperless-Kontos, einschließlich Eigentum, besitzerloser Dokumente sowie direkter und Gruppenfreigaben. Die allgemeine Dokumentleseberechtigung muss ebenfalls vorhanden sein. Maßgeblich sind die in Paperless gespeicherten Rechte und Gruppenmitgliedschaften; IdP-Gruppen- und Rollen-Claims vergeben in der Searchbar keine Rechte. Änderungen in Paperless wirken beim nächsten Request ohne erneute Anmeldung.

Unter **Verwaltung → Benutzer** erscheinen E-Mail und Paperless-Konto-ID. Hier können lokale Adminrechte, Sperren und die separate Download-Freigabe geändert werden. OIDC-Konten haben kein lokales Freigabeprofil; auch Searchbar-Adminrechte umgehen ihre Paperless-Dokumentrechte nicht. Der lokale Admin-Code bleibt als Zugang bei einem OIDC-Ausfall verfügbar.

### Interne Paperless-Anmeldung einrichten

Für Dokumentanfragen verwendet die Searchbar die offizielle [Remote-User-API-Anmeldung](https://docs.paperless-ngx.com/configuration/#PAPERLESS_ENABLE_HTTP_REMOTE_USER_API). In der **Paperless-Konfiguration** die API-Anmeldung aktivieren und den Header festlegen:

```dotenv
PAPERLESS_ENABLE_HTTP_REMOTE_USER_API=true
PAPERLESS_HTTP_REMOTE_USER_HEADER_NAME=HTTP_REMOTE_USER
```

In der **Searchbar-`.env`** denselben Wert für `PAPERLESS_HTTP_REMOTE_USER_HEADER_NAME` setzen. Ohne Angabe gilt `HTTP_REMOTE_USER`. Eigene Header sind möglich, zum Beispiel in beiden Diensten:

```dotenv
PAPERLESS_HTTP_REMOTE_USER_HEADER_NAME=HTTP_X_AUTH_USER
```

Die Searchbar übersetzt den Django-Namen in den tatsächlichen HTTP-Header: `HTTP_REMOTE_USER` → `Remote-User`, `HTTP_X_AUTH_USER` → `X-Auth-User`. Erlaubt sind Namen im Format `HTTP_` mit Großbuchstaben, Ziffern und durch Unterstriche getrennten Bestandteilen. Authentifizierungs- und Transportheader wie `Authorization`, `Cookie`, `Host` oder `Range` können nicht als Benutzerheader verwendet werden.

`PAPERLESS_ENABLE_HTTP_REMOTE_USER` für die normale Web-Anmeldung wird dafür nicht benötigt. `PAPERLESS_AUTO_LOGIN_USERNAME` muss deaktiviert bleiben. Bereits vorhandene Paperless-Konten werden über ihre ID geprüft; nur deren aktueller Benutzername wird intern im konfigurierten Benutzerheader übertragen. Dieser Benutzername muss für HTTP-Header aus druckbaren ASCII-Zeichen ohne Leerzeichen bestehen.

`PAPERLESS_URL` der Searchbar muss direkt auf den internen Paperless-Dienst zeigen, etwa `http://paperless:8000`, in einem Netz mit ausschließlich vertrauenswürdigen Diensten. Dokumentanfragen senden weder den technischen Token noch Browser-Cookies. Jede eingehende Anfrage erhält einen eigenen HTTP-Client; Rechte und Dokumente werden nicht dauerhaft zwischengespeichert. Benutzer- und Filterkataloge liest die App weiterhin mit dem technischen Token. Weitere Objektberechtigungen der OIDC-Benutzer werden nicht geprüft.

Der öffentliche **Paperless-Reverse-Proxy** muss den konfigurierten Benutzerheader aus eingehenden Anfragen entfernen (standardmäßig `Remote-User`, im obigen Beispiel `X-Auth-User`). Andernfalls könnten externe Aufrufer einen Benutzernamen selbst vorgeben. Keine öffentlich erreichbare Paperless-Portfreigabe neben dem Proxy belassen. Beispiel für Traefik-Labels am Paperless-Dienst (Routernamen anpassen; bestehende Middleware beibehalten):

```yaml
labels:
  traefik.http.middlewares.paperless-strip-remote.headers.customrequestheaders.Remote-User: ""
  traefik.http.routers.paperless.middlewares: paperless-strip-remote@docker
```

Bei Nginx im öffentlichen Paperless-`location`-Block:

```nginx
proxy_set_header Remote-User "";
```

Die Proxy-Beispiele verwenden den Standardheader. Bei `HTTP_X_AUTH_USER` darin jeweils `Remote-User` durch `X-Auth-User` ersetzen.

Diese Änderungen gehören zur separat betriebenen Paperless-Instanz. Das Searchbar-Traefik-Overlay konfiguriert ausschließlich die Searchbar und sichert den Paperless-Router nicht automatisch ab. Benutzerkonten vor der ersten Searchbar-Anmeldung in Paperless anlegen. Bei fehlender API-Anmeldung oder verweigertem Zugriff gibt es keinen Rückfall auf den technischen Token.

Logout beendet die App-Sitzung. Es führt keinen globalen Logout beim Identity Provider aus.

## Freigabeprofile und Gastcodes

Unter **Verwaltung → Freigabeprofile** ein Profil über Formularfelder erstellen. Jeder Gastcode bekommt genau ein Profil. OIDC-Benutzer verwenden ausschließlich ihre Paperless-Dokumentrechte.

Beispiel „Buchhaltung Firma A“:

- Erlaubter Speicherpfad: **Buchhaltung**.
- Custom Field **Mandant** ist gleich **Firma A**.

Beide Bedingungen müssen zutreffen. Mehrere erlaubte Speicherpfade, Korrespondenten oder Dokument-IDs gelten innerhalb ihres Kriteriums alternativ. Bei Custom Fields erlaubt „ist einer von“ mehrere Werte; ein Feld darf je Profil einmal vorkommen. Verschiedene Kriterien werden mit UND verknüpft.

Nicht gesetzte Kriterien schränken nicht ein. Ein vollständig leeres Profil erlaubt **kein** Dokument. Für vollständigen Zugriff ausdrücklich **Alle Dokumente erlauben** auswählen. Lokale Administratoren haben vollständigen Zugriff innerhalb der Leserechte des technischen Paperless-Benutzers.

Freigaben umfassen die Dokumentvorschau und deren angezeigte Metadaten. Es gibt keine Schwärzung von Dokumentinhalten oder einzelnen Custom Fields. Gelöschte beziehungsweise nicht lesbare Profilreferenzen sperren das Profil; die Verwaltung zeigt den Fehler an. Auch einzelne gelöschte Dokument-IDs müssen aus einem Profil entfernt werden.

Unter **Verwaltung → Zugangscodes** einen benannten Code mit Profil und Ablauf anlegen. Voreinstellungen: eine Stunde, 24 Stunden, sieben Tage oder individuelles Datum. Der Code wird einmal angezeigt und kann bis zum Ablauf mehrfach verwendet werden. Bewahre ihn nur so lange auf, wie er benötigt wird. Die App speichert ausschließlich einen HMAC-Hash.

Widerruf, Benutzersperren und Profiländerungen wirken beim nächsten Request, auch in bestehenden Sitzungen. Sitzungen laufen maximal zwölf Stunden und spätestens beim Ablauf des Gastcodes aus. Lokale Admin-Codes selbst laufen nicht ab; nach Sitzungsablauf kann derselbe Code erneut verwendet werden, bis er per CLI ersetzt wird. Die Oberfläche prüft die Sitzung regelmäßig; eine bereits heruntergeladene Datei kann nicht zurückgerufen werden.

Downloads lassen sich unabhängig vom Freigabeprofil pro **Benutzer** und pro **Zugangscode** unter „Download erlauben“ aktivieren. Standardmäßig ist die Einstellung aus, auch für Administratoren. Bei Benutzern mit „Benutzer speichern“ übernehmen; bei bestehenden Zugangscodes wird die Checkbox direkt gespeichert. Neue Zugangscodes können bereits beim Anlegen freigeschaltet werden.

Ohne Freigabe blendet die Dokumentansicht den Download-Button aus und der Download-Endpunkt antwortet mit 403. Änderungen gelten beim nächsten Request auch für bestehende Sitzungen; die Oberfläche aktualisiert die Einstellung bei Fokus und regelmäßig. PDF-Vorschau und Thumbnails bleiben verfügbar. Die Einstellung verhindert nicht das Speichern von bereits zur Anzeige übertragenen Vorschauinhalten.

## Suchverhalten

- Eine Suche per Dokument-ID öffnet einen erlaubten Treffer direkt in der Dokumentansicht. Eine interne Dokument-ID entspricht der ID in einer Paperless-URL wie `/documents/123/`; sie ist keine Archivseriennummer (ASN).
- Speicherpfade werden nach dem Namen des konfigurierten Paperless-Objekts gewählt, nicht nach einem physischen Dateipfad. Dokumenttypen sind ein weiterer kombinierbarer Suchfilter.
- Die Auswahllisten in Suche und Verwaltung lassen sich direkt im geöffneten Dropdown durchsuchen. Mehrfachauswahl bleibt beim Filtern erhalten. Kurze Auswahlen wie Ja/Nein bleiben einfache Selects.
- Alle eingegebenen Suchkriterien gelten gemeinsam. Mindestens ein Kriterium ist erforderlich. Es gibt keine Volltext-, Tag-, ASN- oder allgemeine Datumssuche.
- Unter **Verwaltung → Suchfelder** legt ein Administrator bis zu acht Custom Fields fest, die als feste Eingaben in der Suche erscheinen. Anfangs sind keine Custom Fields aktiviert. Die Auswahl wird dauerhaft gespeichert.
- Suchfelder verwenden ausschließlich exakte Übereinstimmung, auch bei direkten API-Aufrufen. Leere Eingaben setzen keinen Filter; „Nein“ und die Zahl 0 sind gültige Suchwerte. Auswahlfelder verwenden eine Option, Dokumentverknüpfungen eine vollständige Liste von IDs.
- Geldbeträge als Zahl ohne Währung eingeben. Textgleichheit verwendet die Paperless-Semantik und berücksichtigt Groß-/Kleinschreibung. Die erweiterten Operatoren bleiben für Freigabeprofile verfügbar; deren Regeln gelten unabhängig von den aktivierten Suchfeldern.
- Maximal acht Custom-Field-Filter pro Suche oder Profil. Paperless begrenzt die kombinierte Abfrage auf 20 atomare Bedingungen; umfangreiche Kombinationen werden verständlich abgelehnt, ohne Freigaben wegzulassen.
- Ergebnisse enthalten 25 Dokumente je Seite, sortiert nach absteigender ID. Jeder Treffer zeigt ein Thumbnail, den Dokumentnamen, beschriftete Basisdaten und die aktivierten Custom Fields. Thumbnails werden bedarfsgerecht und mit derselben Rechteprüfung wie Dokumentdateien geladen; bei fehlenden Bildern erscheint ein Platzhalter. Die aktuelle Dokumentversion wird angezeigt.
- Vorschau mit PDF.js, Seitenwahl und Zoom, sofern Paperless eine PDF-Vorschau liefert. Andere Dateien lassen sich mit aktivierter Download-Freigabe herunterladen. Bild-, HTML- oder Office-Dateien werden nicht aktiv in der App gerendert.

Die API filtert bereits in Paperless vor Trefferzählung und Pagination. Bei Gastzugängen werden Auswahlvorschläge ebenfalls mit dem Freigabeprofil geprüft; bei sehr vielen Korrespondenten oder Auswahloptionen kann der erste Abruf deshalb länger dauern. OIDC-Benutzer sehen die über den technischen Token verfügbaren Filterkataloge ohne zusätzliche Objektberechtigungsprüfung. Ihre Dokumentergebnisse werden direkt in Paperless unter ihrer eigenen Identität gefiltert, gezählt und paginiert, auch bei großen Archiven. Dokumente werden nicht indexiert oder dauerhaft lokal zwischengespeichert.

## Entwicklung und Tests

Voraussetzungen: Python 3.14, `uv`, Node.js 24 ab 24.15 und npm. TypeScript ist wegen der derzeitigen Kompatibilität von `vue-tsc` auf die stabile 6.x-Reihe begrenzt.

```sh
uv sync --locked
npm --prefix frontend ci
```

Für die lokale Entwicklung `.env` mit einer lokalen Datenbankadresse (`DATABASE_URL=sqlite:///./development.db`) und `APP_URL=http://localhost:5173` konfigurieren. Anschließend:

```sh
uv run python -m searchbar.cli init-db
uv run python -m searchbar.cli admin-code
uv run uvicorn searchbar.app:create_app --factory --host 127.0.0.1 --port 8000 --reload --no-access-log
```

In einem zweiten Terminal:

```sh
npm --prefix frontend run dev
```

Die Vite-Oberfläche unter <http://localhost:5173> verwendet einen Proxy zur API. Für den Produktionsbuild `npm --prefix frontend run build` ausführen; anschließend kann FastAPI die gebaute Oberfläche direkt ausliefern. Dafür `APP_URL` auf die tatsächlich verwendete Origin setzen.

Prüfungen:

```sh
uv run ruff check backend tests e2e
uv run ruff format --check backend tests e2e
uv run pytest -q
npm --prefix frontend run format:check
npm --prefix frontend run test
npm --prefix frontend run build
cd frontend
npx playwright install --with-deps chromium
npm run e2e
```

Browserprüfungen starten eine isolierte Test-App auf Port 18765 mit temporärer SQLite-Datenbank, Paperless-Fixtures und einem lokalen OIDC-Provider mit signierten Tokens. Mit `SEARCHBAR_E2E_PORT` kann ein anderer freier Testport gewählt werden; ein Entwicklungsserver auf Port 8000 kann weiterlaufen. Die Test-App und ihre Zugangsdaten sind nicht im Laufzeitimage enthalten.

Containerprüfung:

```sh
docker build -t searchbar:test .
scripts/docker-smoke.sh searchbar:test
```

Der Smoke-Test prüft Start mit leerem Volume, Schemainitialisierung, Nicht-Root-Ausführung, HTTP-Auslieferung und Persistenz nach Neustart. Er entfernt seine temporären Container und Volumes anschließend.

### Prüfung gegen eine echte Paperless-v3-Instanz

Die automatisierten Vertragstests basieren auf der v3-Filterstruktur und decken Suchtypen, Rechte, ID-Aufrufe und Dateiübertragung ab. Für einen echten Instanztest:

1. Einen Test-Lesebenutzer und zwei Dokumente mit unterschiedlichen Speicherpfaden, Korrespondenten und Custom-Field-Werten bereitstellen.
2. Die App mit dem Test-Token verbinden. Ein Profil erstellen, das nur eines der Dokumente erlaubt, und einen Gastcode ausstellen.
3. Mit dem Gastcode per ID, Custom Field, Speicherpfad und Korrespondent suchen. Nur das freigegebene Dokument darf erscheinen; auch Kombinationen und Trefferzahlen prüfen.
4. Die ID des anderen Dokuments direkt unter `/documents/ID` sowie in den API-Dateiendpunkten aufrufen. Erwartet wird 404 ohne fremde Metadaten.
5. PDF-Vorschau und Bearbeitungslink prüfen. Download zunächst deaktiviert prüfen, anschließend für den Testzugang aktivieren und erneut prüfen. Profil ändern beziehungsweise Code widerrufen und denselben Zugriff mit der bestehenden Sitzung wiederholen.
6. Zwei Paperless-Konten mit bestätigten OIDC-E-Mail-Adressen und unterschiedlichen Gruppenrechten verwenden. Ohne lokale Profilzuweisung anmelden und erlaubte sowie fremde Dokumente über Suche, Details, Vorschau, Thumbnail und Download prüfen. Trefferzahl und Pagination müssen den jeweiligen Paperless-Rechten entsprechen.
7. Gruppenfreigabe entziehen oder Paperless-Konto deaktivieren und dieselbe Sitzung weiterverwenden: Der nächste Request muss den Zugriff verweigern. Ein lokales Searchbar-Adminrecht darf fremde Dokumente nicht sichtbar machen. Download-Freigabe separat aktivieren und deaktivieren.
8. Ohne Paperless-Cookie oder Token den öffentlichen Paperless-Endpunkt `/api/documents/` mit dem konfigurierten Header, etwa `X-Auth-User: <Testbenutzer>`, aufrufen: Es darf keine erfolgreiche Dokumentantwort geben. Den Header auch über die Searchbar einsenden; er darf die angemeldete Identität nicht verändern. Bei fehlender Remote-User-Konfiguration muss OIDC-Dokumentzugriff scheitern.

## API

Die eigene API liegt unter `/api`. Die OpenAPI-Beschreibung unter `/api/openapi.json` ist nach Admin-Anmeldung verfügbar. Wesentliche Endpunkte:

| Methode | Pfad | Zweck |
| --- | --- | --- |
| GET | `/api/auth/session` | Sitzung, CSRF-Token, `has_access` und optionaler `access_error`; erzeugt bei Bedarf eine anonyme Sitzung. |
| POST | `/api/auth/code`, `/api/auth/logout` | Anmeldung beziehungsweise Abmeldung. |
| GET | `/api/auth/oidc/login`, `/api/auth/oidc/callback` | OIDC-Anmeldung. |
| GET | `/api/filters` | Zulässige Filterdefinitionen und Auswahlvorschläge einschließlich `document_types`. |
| POST | `/api/documents/search` | Typisierte Suche mit Pagination und optionaler `document_type`-ID; Custom Fields nur aktiviert und exakt. |
| GET | `/api/admin/filters` | Vollständiger Feldkatalog für die Verwaltung. |
| GET/PUT | `/api/admin/search-settings` | Sichtbare Custom-Field-Suchfelder lesen/konfigurieren. |
| GET | `/api/documents/{id}` | Geprüfte Dokumentdetails. |
| GET | `/api/documents/{id}/preview`, `/api/documents/{id}/download` | Geprüfter Datei-Stream mit Range-Unterstützung. |
| GET | `/api/documents/{id}/thumb` | Geschütztes Thumbnail (WebP, PNG oder JPEG), ohne persistenten Browsercache. |
| GET/POST/PUT/DELETE | `/api/admin/profiles` bzw. `/{id}` | Profile verwalten; verwendete Profile können nicht gelöscht werden. |
| GET/PUT | `/api/admin/users` bzw. `/{id}` | Paperless-Zuordnung (`verified_email`, `paperless_user_id`, `paperless_link_error`) lesen; `active`, `is_admin` und `allow_download` ändern. Kein `profile_id`. Ohne `allow_download` bleibt dessen Einstellung erhalten. |
| GET/POST | `/api/admin/codes` | Codes auflisten oder erstellen; `allow_download` ist standardmäßig `false`. |
| PATCH | `/api/admin/codes/{id}` | Download-Freigabe über `allow_download` ändern (nur Admin). |
| POST | `/api/admin/codes/{id}/revoke` | Code widerrufen. |
| GET | `/health` | Lokaler Prozess- und Datenbankcheck, ohne Paperless-Abhängigkeit. |

Zustandsändernde Requests einschließlich Such-POSTs benötigen das Sitzungs-Cookie und `X-CSRF-Token`. Nicht deklarierte Eingabefelder werden abgelehnt. Es gibt keinen allgemeinen Paperless-Proxy und keine schreibenden Dokumentendpunkte.

## Backups, Updates und Wiederherstellung

SQLite arbeitet im WAL-Modus. Für ein konsistentes Dateibackup die App stoppen und das **gesamte** Volume einschließlich eventueller WAL-Dateien sichern. `.env` beziehungsweise die extern gespeicherten Secrets gesondert sichern; sie gehören nicht ins Repository.

Beispiel für das mitgelieferte Compose-Projekt:

```sh
docker compose stop searchbar
docker compose run --rm --no-deps --entrypoint tar searchbar -C /data -czf - . > searchbar-data.tar.gz
docker compose start searchbar
```

Zur Wiederherstellung ein leeres Datenvolume bei gestoppter App verwenden und entpacken:

```sh
cat searchbar-data.tar.gz | docker compose run --rm -T --no-deps --entrypoint tar searchbar -C /data -xzf -
docker compose up -d
```

Denselben `SECRET_KEY` wiederherstellen, wenn vorhandene Gast- und Admin-Codes weiterhin funktionieren sollen. Backups und Secrets enthalten Zugangsdaten beziehungsweise deren Prüfinformationen und sollten nur den zuständigen Betreibern zugänglich sein.

Der Container erstellt das aktuelle Schema beim Start über `init-db`. Wiederholte Starts erhalten Daten einer Datenbank mit diesem Schema. Diese noch nicht veröffentlichte Version unterstützt ausschließlich frische Installationen: Es gibt keine Migration oder Übernahme älterer Entwicklungsschemata. Für solche Testdaten eine neue separate Datenbank verwenden. Backups nur mit der passenden Schema-/App-Version wiederherstellen.

## CI und Image-Veröffentlichung

GitHub Actions prüft Python-Code, Backendtests, Vue-Komponenten, TypeScript, Frontendbuild und Browserabläufe. Danach wird ein Container gebaut und mit dem Smoke-Test geprüft. Erst wenn diese Prüfungen erfolgreich sind, veröffentlicht ein Push-Workflow Images für `linux/amd64` und `linux/arm64` nach `ghcr.io/david-loe/paperless-searchbar`.

- Pull Requests veröffentlichen nichts.
- Pushes auf `main` veröffentlichen `edge` und einen `sha-…`-Tag.
- Tags wie `v1.2.3` veröffentlichen `1.2.3`, `1.2` und `latest`.
- Vorabversionen wie `v1.2.3-rc.1` erhalten ihren Vorabversions-Tag, aktualisieren aber nicht `latest`.
- Alle verwendeten Actions sind auf Commit-SHAs festgeschrieben. Dependabot prüft die Abhängigkeiten wöchentlich.

Die Registry-Anmeldung verwendet `GITHUB_TOKEN` mit `packages:write`. GitHub Actions und Paketschreibrechte müssen im Repository erlaubt sein. Für anonymes Pulling die Paketsichtbarkeit in GHCR auf öffentlich stellen; andernfalls vorher mit einem passenden GitHub-Token bei GHCR anmelden. Der Workflow deployt nicht automatisch auf einen Server.

## Fehlersuche

- **502 bei Suche:** Erreichbarkeit, Token sowie Modell- und Objektleserechte des technischen Paperless-Benutzers prüfen.
- **Ungültiges Profil:** Gelöschte oder für den technischen Benutzer nicht mehr lesbare Dokumente, Speicherpfade, Korrespondenten, Felder oder Auswahloptionen im Profil korrigieren.
- **OIDC-Anmeldung fehlgeschlagen:** Issuer, Client-Konfiguration, genaue Callback-URI, Erreichbarkeit des Providers und Systemzeit prüfen. Die App gibt Tokens und Provider-Fehlerdetails nicht im Browser aus.
- **OIDC ohne Dokumentzugriff:** Den angezeigten Hinweis prüfen: bestätigte eindeutige E-Mail, aktives Paperless-Konto und Dokumentleserechte. Bei verweigerten Dokumentanfragen zusätzlich die interne URL und Remote-User-API-Konfiguration prüfen.
- **CSRF-Fehler:** `APP_URL` muss exakt zur Browser-Origin passen. Nach einem Sitzungswechsel die Seite neu laden.
- **Keine Anmeldung hinter HTTPS:** `APP_URL`, Cookie-Einstellungen und Proxy-Konfiguration prüfen. Bei `https://` wird das Cookie nicht über unverschlüsseltes HTTP übertragen.
- **429 bei Anmeldung:** Nach mehr als 15 Versuchen pro Client-IP innerhalb von fünf Minuten warten. Hinter einem Proxy dessen Adresse korrekt als vertrauenswürdig konfigurieren, damit Clients getrennt begrenzt werden.
- **Container startet nicht:** `docker compose logs searchbar` auf Konfigurations-, Volume- oder Schemafehler prüfen. API-Access-Logs sind standardmäßig deaktiviert, damit OIDC-Callbackcodes und Suchparameter nicht protokolliert werden.

Siehe [PLAN.md](PLAN.md) für die Architektur. Lizenz: [GNU AGPL v3](LICENSE).
