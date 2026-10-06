# Implementierungsplan: Paperless Searchbar

## Ziel und festgelegter Umfang

Eine schlanke, deutschsprachige Web-App zum Durchsuchen und Anzeigen von Dokumenten einer Paperless-ngx-v3-Instanz. Gesucht wird ausschließlich nach interner Dokument-ID, Custom Fields, Speicherpfad und Korrespondent. Dokumente können angesehen und heruntergeladen werden; zum Bearbeiten führt ein Link in die Paperless-Instanz.

Zugang erhalten Benutzer über OIDC oder zeitlich begrenzte Gastcodes. Die App verwaltet eigene Freigabeprofile und verwendet für Paperless einen technischen Benutzer mit Leserechten.

Festgelegte Grenzen der ersten Version:

- Eine Paperless-Instanz, ein OIDC-Provider und eine App-Instanz.
- Genau ein Freigabeprofil pro Gastcode beziehungsweise freigeschaltetem OIDC-Benutzer.
- Freigaben gelten für das gesamte Dokument einschließlich angezeigter Metadaten, Custom Fields, Vorschau und Download.
- Keine Volltext-, ASN-, Tag- oder Datumssuche. Datumswerte innerhalb von Custom Fields bleiben durchsuchbar.
- Keine Dokumentbearbeitung, Uploads oder schreibenden Dokumentoperationen.
- Keine OIDC-Gruppenzuordnung, lokale Dokumentkopie oder eigener Suchindex.
- HTTPS und Zertifikate übernimmt ein Reverse Proxy, beispielsweise Traefik.

Die Phasen werden in der aufgeführten Reihenfolge umgesetzt. Eine Veröffentlichung erfolgt erst nach erfolgreicher Prüfung aller Phasen.

## Phase 1 – Projektgrundlage und Architektur

### Umsetzung

- Backend mit Python 3.14, FastAPI, Pydantic, HTTPX, SQLAlchemy und Alembic aufsetzen. Python-Abhängigkeiten mit `uv` verwalten.
- Frontend mit **Vue 3**, Composition API, Single-File Components, TypeScript, Vue Router, Vite und Tailwind CSS aufsetzen. Node-Abhängigkeiten mit npm verwalten.
- Aktuelle stabile, miteinander kompatible Paketversionen zum Implementierungszeitpunkt prüfen und durch `uv.lock` und `package-lock.json` festschreiben. Keine Vorabversionen einsetzen.
- Repository in Backend, Frontend und Integrationstests gliedern. Bestehende Lizenz erhalten.
- SQLite für Benutzer, Freigabeprofile, Gastcodes und Sitzungen verwenden. Datenbank und persistente App-Daten unter `/data` ablegen.
- Datenmodelle und Alembic-Migrationen vorbereiten: Benutzer mit optionaler OIDC-Identität oder gehashtem lokalem Admin-Code, separate Admin-Rolle, Freigabeprofil, Gastcode und serverseitige Sitzung.
- Konfiguration über Umgebungsvariablen beziehungsweise Secret-Dateien bereitstellen: interne Paperless-API-Adresse, öffentliche Paperless-Adresse, Paperless-Token, öffentliche App-Adresse, OIDC-Konfiguration, Sitzungsschlüssel und vertrauenswürdige Proxy-Adressen.
- Oberfläche und eigene API unter derselben Origin ausliefern; API unter `/api`. Lokale Entwicklung mit Vite-Proxy zum Backend ermöglichen.
- Backendtests mit pytest, Frontendtests mit Vitest und Vue Test Utils sowie Browsertests mit Playwright vorbereiten. Ruff und TypeScript-Prüfung einrichten.

### Abnahme

- Backend und Vue-Oberfläche starten lokal reproduzierbar mit den Lockfiles.
- Eine leere Datenbank lässt sich über Alembic initialisieren.
- Konfigurationsfehler werden verständlich gemeldet; Secrets erscheinen nicht in Logs oder Frontend-Bundles.
- Erste Smoke-Tests sowie Python- und TypeScript-Prüfungen laufen erfolgreich.

## Phase 2 – Paperless-Anbindung und typisierte Suche

### Umsetzung

- Einen zentralen HTTPX-Client für die Paperless-v3-REST-API implementieren. Der technische Benutzer erhält nur die erforderlichen Leserechte.
- Interne API-Adresse und öffentliche Paperless-Adresse getrennt behandeln. Alle Bearbeitungslinks aus der öffentlichen Adresse ableiten.
- Typisierte Suchmodelle für interne Dokument-ID, Speicherpfad, Korrespondent und Custom-Field-Filter erstellen. Keine beliebigen Paperless-Queryparameter durchreichen.
- Speicherpfade als konfigurierte Paperless-Speicherpfadobjekte über ihren Namen auswählen; keine Dateisystempfadsuche implementieren.
- Custom-Field-Definitionen und Auswahloptionen aus Paperless lesen und passende Operatoren anbieten:
  - Text und URL: Gleichheit und Enthalten.
  - Zahlen, Geldbeträge und Datum: Gleichheit und Bereich.
  - Boolean: Ja oder Nein.
  - Auswahlfelder: ein oder mehrere ausgewählte Werte.
  - Dokumentverknüpfungen: Dokument-IDs.
  - Vorhanden und leer, soweit für den jeweiligen Feldtyp unterstützt.
- Mehrere Suchkriterien mit UND verknüpfen. Suche nur mit mindestens einem Kriterium ausführen; Ergebnisse paginieren und standardmäßig nach absteigender Dokument-ID sortieren.
- Adapter für Dokumentdetails, aktuelle Dokumentversion, Vorschau und Download implementieren. Dokumente nicht dauerhaft lokal speichern.
- Dateiübertragung einschließlich Range-Requests für PDF-Vorschauen unterstützen. Es gibt keinen allgemeinen Proxy für frei wählbare URLs oder Paperless-Endpunkte.
- Fehler für nicht erreichbares Paperless, ungültigen Token, gelöschte Dokumente und fehlende Vorschau verständlich aufbereiten.
- In dieser Phase die Integration als interne Services und über Tests entwickeln. Dokumentendaten erst nach Umsetzung der Authentifizierung und Freigabeprüfung öffentlich über die App-API bereitstellen.

### Abnahme

- Tests decken alle Suchtypen, gültige und ungültige Werte, Kombinationen und Pagination ab.
- Vertragstests mit Paperless-v3-Testdaten prüfen die übersetzten Filter und Antwortmodelle.
- Der Client führt ausschließlich lesende Paperless-Aufrufe aus.
- API-Ausfälle oder unerwartete Antworten führen zu kontrollierten Fehlermeldungen.

## Phase 3 – Anmeldung und Sitzungen

### Umsetzung

- Lokalen Admin mit `python -m searchbar.cli admin-code` anlegen; einen zufälligen Zugangscode einmalig anzeigen und ausschließlich als HMAC-Hash speichern. Der Code gilt bis zum Ersetzen. Erneutes Ausführen ersetzt ihn und beendet alte Admin-Sitzungen; `--name` wählt optional eine andere interne lokale Kennung.
- OIDC mit Authlib und Discovery implementieren: Authorization Code Flow mit PKCE, State, Nonce und Prüfung des ID-Tokens.
- OIDC-Benutzer eindeutig über Issuer und Subject identifizieren. Neue Benutzer ohne Dokumentrechte anlegen und auf die ausstehende Freigabe hinweisen.
- Benannte, kryptografisch zufällige Gastcodes erzeugen. Codes nur bei Erstellung vollständig anzeigen und ausschließlich gehasht speichern.
- Gastcodes bis zum Ablauf mehrfach nutzbar machen. Laufzeitvorgaben: eine Stunde, 24 Stunden als Standard, sieben Tage oder individueller Ablaufzeitpunkt.
- Ablauf und Widerruf serverseitig durchsetzen; laufende Gast-Sitzungen beim nächsten Request entsprechend ablehnen.
- Serverseitige Sitzungen mit HttpOnly-Cookies und maximal zwölf Stunden Laufzeit implementieren. Gast-Sitzungen enden spätestens beim Ablauf des zugehörigen Codes.
- Cookie- und Proxy-Konfiguration für externes HTTPS bereitstellen, CSRF-Schutz auf zustandsändernde Requests anwenden und Loginversuche begrenzen.
- Login-, Logout- und Sitzungsendpunkte für die Vue-Oberfläche bereitstellen. Lokale Administratoren und Gäste verwenden dasselbe Code-Feld und denselben Anmeldeendpunkt; es gibt keine Benutzername-/Passwortanmeldung. Das Backend bestimmt die Rechte anhand des Codes. OIDC bleibt als weitere Anmeldemöglichkeit erhalten.

### Abnahme

- Lokaler Admin-Code, OIDC und Gastcode erlauben die jeweils vorgesehene Anmeldung. Admin-Code-Rotation sperrt den alten Code und alle zugehörigen Sitzungen; Admin-Sitzungen laufen nach zwölf Stunden ab.
- Tests prüfen ungültige OIDC-Antworten, Identitätszuordnung, Sessionablauf, Logout, Codeablauf und Widerruf.
- Wiederholte Loginversuche werden begrenzt; CSRF-Prüfungen greifen.
- Ein neuer OIDC-Benutzer kann sich anmelden, aber noch keine Dokumente abrufen.

## Phase 4 – Freigabeprofile und geschützte App-API

### Umsetzung

- Wiederverwendbare Freigabeprofile für Dokument-IDs, Speicherpfade, Korrespondenten und Custom-Field-Werte implementieren.
- Unterschiedliche Kriterien mit UND, mehrere zugelassene Werte desselben Kriteriums mit ODER verbinden. Nicht gesetzte Kriterien schränken nicht ein.
- Ein vollständig leeres Profil gewährt keinen Zugriff. Uneingeschränkter Zugriff erfordert eine ausdrückliche Auswahl „Alle Dokumente“.
- Genau ein Profil pro Gastcode beziehungsweise freigeschaltetem OIDC-Benutzer zuweisen. Die separate Admin-Rolle erhält vollständigen Zugriff innerhalb der Leserechte des technischen Paperless-Benutzers.
- Suchfilter und Freigabekriterien serverseitig zwingend miteinander verknüpfen, bevor Paperless Treffer zählt oder paginiert. Benutzerfilter dürfen Freigabefilter niemals ersetzen oder abschwächen.
- Dieselbe Freigabeprüfung für direkte Dokumentdetails, Vorschau und Download verwenden. Änderungen an Profilen oder Dokumentzuordnungen beim nächsten Zugriff berücksichtigen.
- Nicht erlaubte und nicht vorhandene Dokumente mit derselben 404-Antwort behandeln.
- Auswahlvorschläge für Speicherpfade und Korrespondenten nur nennen, wenn innerhalb der Freigabe passende Dokumente existieren. Custom-Field-Wertvorschläge dürfen keine Werte fremder Dokumente offenlegen.
- Gelöschte oder ungültige Referenzen in Freigaben sperren den betroffenen Zugriff und erzeugen eine verständliche Admin-Meldung. Einschränkungen niemals stillschweigend entfernen.
- Typisierte App-Endpunkte für Filterdefinitionen, Auswahlvorschläge, Suche, Dokumentdetails, Vorschau und Download bereitstellen; Schnittstellen über OpenAPI beschreiben.
- Admin-Endpunkte für Profile, Gastcodes, Benutzerfreigaben, Benutzersperren und Admin-Zuweisungen implementieren. Admin-Rechte ausschließlich serverseitig prüfen.
- Private Antworten vor öffentlichem Caching schützen. Paperless-Tokens ausschließlich im Backend halten.

### Abnahme

- Berechtigungstests prüfen UND/ODER-Verknüpfung, leere Profile, „Alle Dokumente“ und Kombinationen mit Benutzerfiltern.
- Manipulierte Parameter und direkt aufgerufene Dokument-IDs umgehen keine Freigabe.
- Trefferzahlen, Auswahlvorschläge, Metadaten, Vorschauen und Downloads geben keine fremden Dokumentinformationen preis.
- Profiländerungen, Benutzersperren und Codewiderruf wirken beim nächsten Request auch in bestehenden Sitzungen.
- Nichtadministratoren können keine Verwaltungsaktionen ausführen.

## Phase 5 – Vue-Oberfläche für Suche, Ansicht und Verwaltung

### Umsetzung

- Eine responsive deutsche Oberfläche mit klaren Formularen, Tastaturbedienung, Fokuszuständen und verständlichen Lade-, Leer- und Fehlerzuständen bauen.
- Loginseite mit einem gemeinsamen Zugangscode-Feld für Gäste und lokale Administratoren sowie OIDC bereitstellen.
- Suchseite mit Dokument-ID, durchsuchbaren Auswahllisten für Speicherpfad und Korrespondent sowie hinzufügbaren, typgerechten Custom-Field-Filtern implementieren.
- Suche explizit per Schaltfläche oder Enter ausführen. Keine Volltextsuche ergänzen.
- Paginierte Trefferliste mit ID, Titel, Datum, Korrespondent und Speicherpfad anzeigen.
- Detailansicht mit Metadaten, Custom Fields, PDF-Vorschau, Download und „In Paperless bearbeiten“ bauen. Die aktuelle Dokumentversion anzeigen; bei nicht darstellbaren Dateiformaten Download anbieten.
- Den Bearbeitungslink zur öffentlichen Paperless-Instanz öffnen. Dort gelten deren eigene Anmeldung und Berechtigungen.
- Admin-Oberfläche für Profile, OIDC-Benutzer und Gastcodes erstellen. Profile über Formularfelder statt JSON bearbeiten.
- Neue OIDC-Benutzer ohne Freigabe sichtbar auflisten; Profilzuweisung, Sperrung und Admin-Zuweisung ermöglichen.
- Gastcodes mit Bezeichnung, Profil, Ablauf und Status auflisten. Einmalige Codeanzeige mit Kopierfunktion und expliziten Widerruf anbieten.

### Abnahme

- Playwright prüft Gastanmeldung → Suche → Dokumentansicht → Download.
- Ein weiterer Ablauf prüft OIDC-Anmeldung → ausstehende Freigabe → Admin-Zuweisung → Dokumentzugriff.
- Vue-Komponententests prüfen typgerechte Filtereingaben und relevante Formularvalidierung.
- Oberfläche funktioniert auf Desktop und mobilen Viewports sowie per Tastatur.
- Abgelaufene Sitzungen und Backendfehler führen zu verständlichen Zuständen ohne Weiteranzeige geschützter Daten aus vorherigen Ansichten.

## Phase 6 – Container und Betriebsdokumentation

### Umsetzung

- Multi-Stage-Dockerbuild für Vue-Assets und Python-Backend erstellen. Node wird nur zum Bauen benötigt; das Laufzeitimage liefert Assets und API aus.
- Container ohne Root auf HTTP-Port 8000 betreiben, persistentes `/data` einbinden und einen Healthcheck bereitstellen.
- Alembic-Migrationen vor dem App-Start ausführen und bei Fehlern kontrolliert abbrechen.
- Compose-Beispiel und vollständige Beispielkonfiguration bereitstellen; optionale Traefik-Anbindung dokumentieren.
- Externe HTTPS-Adresse und vertrauenswürdige Proxy-Adressen korrekt für OIDC-Redirects und sichere Cookies berücksichtigen. Keine Zertifikatsverwaltung in die App integrieren.
- README um Installation, Paperless-Lesebenutzer, OIDC-Callback, lokalen Admin-Bootstrap, Gastcodes, Freigabebeispiele und Fehlersuche ergänzen.
- Backup und Wiederherstellung des Datenvolumes, notwendige Secrets sowie den Updateablauf dokumentieren.

### Abnahme

- Docker-Smoke-Test prüft Start mit leerem Volume, Migrationen, Oberfläche und Healthcheck.
- Benutzer, Profile und Sitzungsdaten bleiben bei Container-Neustart erhalten.
- Die initiale Schemaanlage ist wiederholbar; ein Neustart mit vorhandenem Datenvolume erhält die Daten. Ein Upgradepfad von früheren Entwicklungsschemas ist nicht erforderlich.
- Reverse-Proxy-Konfiguration erzeugt korrekte öffentliche OIDC-Redirects und Cookie-Einstellungen.
- Ein dokumentierter Integrationstest gegen eine echte Paperless-v3-Instanz ergänzt die automatisierten Vertragstests.

## Phase 7 – GitHub Actions und automatische Veröffentlichung

### Umsetzung

- Pull Requests mit Backendtests, Vue-Tests, TypeScript-Prüfung, Ruff, Frontendbuild und den wesentlichen Browserabläufen prüfen.
- Containerbuild und Smoke-Test in die CI aufnehmen. Veröffentlichung von erfolgreichen Prüfungen abhängig machen.
- Images für `linux/amd64` und `linux/arm64` bauen.
- Nach erfolgreichen Builds des Standardbranches `edge` und Commit-Tags veröffentlichen.
- Versionstags `v*` als Versions-Tags veröffentlichen; `latest` ausschließlich für stabile Releases aktualisieren.
- Zielregistry: `ghcr.io/david-loe/paperless-searchbar`. Authentifizierung mit `GITHUB_TOKEN`, passende minimale Workflow-Berechtigungen und OCI-Metadaten konfigurieren.
- GitHub Actions auf konkrete Commit-SHAs festschreiben. Pull-Request-Workflows veröffentlichen keine Images.
- README um Image-Tags, Bezug aus GHCR und Releaseablauf ergänzen. Die Pipeline veröffentlicht das Containerimage; ein automatisches Deployment auf einen Server gehört nicht zum Umfang.

### Abnahme

- Ein Pull Request wird vollständig geprüft, ohne ein Image zu veröffentlichen.
- Ein erfolgreicher Build des Standardbranches veröffentlicht `edge` und den Commit-Tag.
- Ein stabiler Versionstag veröffentlicht die vorgesehenen Versions-Tags und `latest` mit beiden Architekturen.
- Das veröffentlichte Image startet mit dem dokumentierten Compose-Beispiel.

## Referenzen

- [Paperless-ngx REST API](https://docs.paperless-ngx.com/api/)
- [Paperless-ngx Releases](https://github.com/paperless-ngx/paperless-ngx/releases)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Vue](https://vuejs.org/guide/introduction.html)
- [Vite](https://vite.dev/guide/)
- [GitHub Actions: Docker-Images veröffentlichen](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
