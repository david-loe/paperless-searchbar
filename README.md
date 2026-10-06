# Paperless Searchbar

Eine deutschsprachige, rein lesende Web-App für Paperless-ngx v3. Suche nach **interner Dokument-ID, Custom Fields, Speicherpfad und Korrespondent**, öffne die PDF-Vorschau oder lade ein Dokument herunter. Bearbeitet wird über einen Link direkt in Paperless.

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
- Leserechte auf Korrespondenten, Speicherpfade und Custom Fields, die zur Suche und zur Prüfung von Profilen benötigt werden.
- Keine Superuser-, Änderungs-, Upload- oder Löschrechte.

Die App kann nie mehr Dokumente freigeben, als dieser technische Benutzer lesen darf. Benutzer der Searchbar benötigen kein eigenes Paperless-Konto. Der Bearbeitungslink überträgt keine Zugangsdaten; in Paperless gelten dessen eigene Anmeldung und Berechtigungen.

Die App spricht ausschließlich lesende Paperless-Endpunkte an. Vorschauen und Downloads werden nach Freigabeprüfung über das Backend gestreamt. Der Paperless-Token wird nicht an den Browser weitergegeben.

## Konfiguration

| Variable | Bedeutung |
| --- | --- |
| `APP_URL` | Öffentliche Origin der App, z. B. `https://suche.example.com`; ohne Unterpfad. Relevant für OIDC, Cookies und CSRF. |
| `PAPERLESS_URL` | Interne Basisadresse von Paperless, ohne `/api/`. |
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

Nur eine App-Instanz mit einem Worker betreiben. `/data` muss für UID/GID `10001:10001` schreibbar sein; das mitgelieferte benannte Volume wird beim ersten Start passend initialisiert. Ein Bind-Mount benötigt passende Eigentümerrechte. Migrationen laufen vor jedem Start; bei einem Fehler startet die App nicht.

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

Die Identität wird durch **Issuer und Subject** bestimmt, nicht durch die E-Mail-Adresse. Gruppen- und Rollen-Claims vergeben keine Rechte. Nach der ersten Anmeldung erscheint der Benutzer unter **Verwaltung → Benutzer**, zunächst ohne Dokumentzugriff. Dort ein Profil zuweisen oder gezielt Admin-Rechte vergeben. Der lokale Admin-Code bleibt als Zugang bei einem OIDC-Ausfall verfügbar.

Logout beendet die App-Sitzung. Es führt keinen globalen Logout beim Identity Provider aus.

## Freigabeprofile und Gastcodes

Unter **Verwaltung → Freigabeprofile** ein Profil über Formularfelder erstellen. Jeder Benutzer oder Gastcode bekommt genau ein Profil.

Beispiel „Buchhaltung Firma A“:

- Erlaubter Speicherpfad: **Buchhaltung**.
- Custom Field **Mandant** ist gleich **Firma A**.

Beide Bedingungen müssen zutreffen. Mehrere erlaubte Speicherpfade, Korrespondenten oder Dokument-IDs gelten innerhalb ihres Kriteriums alternativ. Bei Custom Fields erlaubt „ist einer von“ mehrere Werte; ein Feld darf je Profil einmal vorkommen. Verschiedene Kriterien werden mit UND verknüpft.

Nicht gesetzte Kriterien schränken nicht ein. Ein vollständig leeres Profil erlaubt **kein** Dokument. Für vollständigen Zugriff ausdrücklich **Alle Dokumente erlauben** auswählen. Administratoren haben vollständigen Zugriff innerhalb der Leserechte des technischen Paperless-Benutzers.

Freigaben umfassen die Dokumentdatei und deren angezeigte Metadaten. Es gibt keine Schwärzung von Dokumentinhalten oder einzelnen Custom Fields. Gelöschte beziehungsweise nicht lesbare Profilreferenzen sperren das Profil; die Verwaltung zeigt den Fehler an. Auch einzelne gelöschte Dokument-IDs müssen aus einem Profil entfernt werden.

Unter **Verwaltung → Zugangscodes** einen benannten Code mit Profil und Ablauf anlegen. Voreinstellungen: eine Stunde, 24 Stunden, sieben Tage oder individuelles Datum. Der Code wird einmal angezeigt und kann bis zum Ablauf mehrfach verwendet werden. Bewahre ihn nur so lange auf, wie er benötigt wird. Die App speichert ausschließlich einen HMAC-Hash.

Widerruf, Benutzersperren und Profiländerungen wirken beim nächsten Request, auch in bestehenden Sitzungen. Sitzungen laufen maximal zwölf Stunden und spätestens beim Ablauf des Gastcodes aus. Lokale Admin-Codes selbst laufen nicht ab; nach Sitzungsablauf kann derselbe Code erneut verwendet werden, bis er per CLI ersetzt wird. Die Oberfläche prüft die Sitzung regelmäßig; eine bereits heruntergeladene Datei kann nicht zurückgerufen werden.

## Suchverhalten

- Eine Suche per Dokument-ID öffnet einen erlaubten Treffer direkt in der Dokumentansicht. Eine interne Dokument-ID entspricht der ID in einer Paperless-URL wie `/documents/123/`; sie ist keine Archivseriennummer (ASN).
- Speicherpfade werden nach dem Namen des konfigurierten Paperless-Objekts gewählt, nicht nach einem physischen Dateipfad.
- Alle eingegebenen Suchkriterien gelten gemeinsam. Mindestens ein Kriterium ist erforderlich. Es gibt keine Volltext-, Tag-, ASN- oder allgemeine Datumssuche.
- Unter **Verwaltung → Suchfelder** legt ein Administrator bis zu acht Custom Fields fest, die als feste Eingaben in der Suche erscheinen. Anfangs sind keine Custom Fields aktiviert. Die Auswahl wird dauerhaft gespeichert.
- Suchfelder verwenden ausschließlich exakte Übereinstimmung, auch bei direkten API-Aufrufen. Leere Eingaben setzen keinen Filter; „Nein“ und die Zahl 0 sind gültige Suchwerte. Auswahlfelder verwenden eine Option, Dokumentverknüpfungen eine vollständige Liste von IDs.
- Geldbeträge als Zahl ohne Währung eingeben. Textgleichheit verwendet die Paperless-Semantik und berücksichtigt Groß-/Kleinschreibung. Die erweiterten Operatoren bleiben für Freigabeprofile verfügbar; deren Regeln gelten unabhängig von den aktivierten Suchfeldern.
- Maximal acht Custom-Field-Filter pro Suche oder Profil. Paperless begrenzt die kombinierte Abfrage auf 20 atomare Bedingungen; umfangreiche Kombinationen werden verständlich abgelehnt, ohne Freigaben wegzulassen.
- Ergebnisse enthalten 25 Dokumente je Seite, sortiert nach absteigender ID. Die aktuelle Dokumentversion wird angezeigt.
- Vorschau mit PDF.js, Seitenwahl und Zoom, sofern Paperless eine PDF-Vorschau liefert. Andere Dateien lassen sich herunterladen. Bild-, HTML- oder Office-Dateien werden nicht aktiv in der App gerendert.

Die API filtert bereits in Paperless vor Trefferzählung und Pagination. Auswahlvorschläge werden ebenfalls mit dem Freigabeprofil geprüft; bei sehr vielen Korrespondenten oder Auswahloptionen kann der erste Abruf deshalb länger dauern. Dokumente werden nicht indexiert oder dauerhaft lokal zwischengespeichert.

## Entwicklung und Tests

Voraussetzungen: Python 3.14, `uv`, Node.js 24 ab 24.15 und npm. TypeScript ist wegen der derzeitigen Kompatibilität von `vue-tsc` auf die stabile 6.x-Reihe begrenzt.

```sh
uv sync --locked
npm --prefix frontend ci
```

Für die lokale Entwicklung `.env` mit einer lokalen Datenbankadresse (`DATABASE_URL=sqlite:///./development.db`) und `APP_URL=http://localhost:5173` konfigurieren. Anschließend:

```sh
uv run alembic upgrade head
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

Der Smoke-Test prüft Start mit leerem Volume, Migrationen, Nicht-Root-Ausführung, HTTP-Auslieferung und Persistenz nach Neustart. Er entfernt seine temporären Container und Volumes anschließend.

### Prüfung gegen eine echte Paperless-v3-Instanz

Die automatisierten Vertragstests basieren auf der v3-Filterstruktur und decken Suchtypen, Rechte, ID-Aufrufe und Dateiübertragung ab. Für einen echten Instanztest:

1. Einen Test-Lesebenutzer und zwei Dokumente mit unterschiedlichen Speicherpfaden, Korrespondenten und Custom-Field-Werten bereitstellen.
2. Die App mit dem Test-Token verbinden. Ein Profil erstellen, das nur eines der Dokumente erlaubt, und einen Gastcode ausstellen.
3. Mit dem Gastcode per ID, Custom Field, Speicherpfad und Korrespondent suchen. Nur das freigegebene Dokument darf erscheinen; auch Kombinationen und Trefferzahlen prüfen.
4. Die ID des anderen Dokuments direkt unter `/documents/ID` sowie in den API-Dateiendpunkten aufrufen. Erwartet wird 404 ohne fremde Metadaten.
5. PDF-Vorschau, Download und Bearbeitungslink prüfen. Profil ändern beziehungsweise Code widerrufen und denselben Zugriff mit der bestehenden Sitzung wiederholen.
6. Mit dem realen OIDC-Provider anmelden, ausstehende Freigabe prüfen, Profil zuweisen und anschließend einen gesperrten Benutzer prüfen.

## API

Die eigene API liegt unter `/api`. Die OpenAPI-Beschreibung unter `/api/openapi.json` ist nach Admin-Anmeldung verfügbar. Wesentliche Endpunkte:

| Methode | Pfad | Zweck |
| --- | --- | --- |
| GET | `/api/auth/session` | Sitzung und CSRF-Token; erzeugt bei Bedarf eine anonyme Sitzung. |
| POST | `/api/auth/code`, `/api/auth/logout` | Anmeldung beziehungsweise Abmeldung. |
| GET | `/api/auth/oidc/login`, `/api/auth/oidc/callback` | OIDC-Anmeldung. |
| GET | `/api/filters` | Zulässige Filterdefinitionen und Auswahlvorschläge. |
| POST | `/api/documents/search` | Typisierte Suche mit Pagination; Custom Fields nur aktiviert und exakt. |
| GET | `/api/admin/filters` | Vollständiger Feldkatalog für die Verwaltung. |
| GET/PUT | `/api/admin/search-settings` | Sichtbare Custom-Field-Suchfelder lesen/konfigurieren. |
| GET | `/api/documents/{id}` | Geprüfte Dokumentdetails. |
| GET | `/api/documents/{id}/preview`, `/api/documents/{id}/download` | Geprüfter Datei-Stream mit Range-Unterstützung. |
| GET/POST/PUT/DELETE | `/api/admin/profiles` bzw. `/{id}` | Profile verwalten; verwendete Profile können nicht gelöscht werden. |
| GET/PUT | `/api/admin/users` bzw. `/{id}` | Benutzer prüfen und Rechte zuweisen. |
| GET/POST | `/api/admin/codes` | Codes auflisten oder erstellen. |
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

Vor Updates ein Backup erstellen, neuen Image-Tag beziehen und den Dienst neu starten. Alembic aktualisiert das Schema vor dem App-Start. Für ein Rollback das alte Image **und** das zugehörige Datenbackup wiederherstellen; ein beliebiges Downgrade einer bereits migrierten Datenbank wird nicht zugesichert.

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
- **CSRF-Fehler:** `APP_URL` muss exakt zur Browser-Origin passen. Nach einem Sitzungswechsel die Seite neu laden.
- **Keine Anmeldung hinter HTTPS:** `APP_URL`, Cookie-Einstellungen und Proxy-Konfiguration prüfen. Bei `https://` wird das Cookie nicht über unverschlüsseltes HTTP übertragen.
- **429 bei Anmeldung:** Nach mehr als 15 Versuchen pro Client-IP innerhalb von fünf Minuten warten. Hinter einem Proxy dessen Adresse korrekt als vertrauenswürdig konfigurieren, damit Clients getrennt begrenzt werden.
- **Container startet nicht:** `docker compose logs searchbar` auf Konfigurations-, Volume- oder Migrationsfehler prüfen. API-Access-Logs sind standardmäßig deaktiviert, damit OIDC-Callbackcodes und Suchparameter nicht protokolliert werden.

Siehe [PLAN.md](PLAN.md) für die Implementierungsphasen. Lizenz: [GNU AGPL v3](LICENSE).
