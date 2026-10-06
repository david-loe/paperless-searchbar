# Architektur der Paperless Searchbar

## Anmeldung und Berechtigungen

- OIDC identifiziert lokale Konten über Issuer und Subject. Eine bestätigte, eindeutige E-Mail-Adresse verbindet sie beim Login mit einem bestehenden Paperless-Konto.
- Paperless-Benutzer-ID, bestätigte E-Mail und ein gegebenenfalls aufgetretener Zuordnungsfehler werden lokal gespeichert. Vor Dokumentanfragen wird das Konto erneut geprüft; Änderungen lösen keine stille Neuzuordnung aus.
- OIDC-Dokumentzugriffe verwenden den über `PAPERLESS_HTTP_REMOTE_USER_HEADER_NAME` konfigurierten Header am internen Paperless-Endpunkt (Standard `HTTP_REMOTE_USER` → `Remote-User`). Jede eingehende Anfrage hat einen eigenen Client samt Cookie-Speicher. Dateistreams halten ihn bis zum Übertragungsende offen.
- Paperless prüft die aktuellen Dokumentrechte und übernimmt Trefferzählung und Pagination. Kein archivweiter Scan, kein dauerhafter Rechtecache und kein Rückfall auf den technischen Token.
- OIDC-Gruppenclaims vergeben keine Searchbar-Rechte. Auch lokale Adminrechte eines OIDC-Kontos umgehen dessen Paperless-Dokumentrechte nicht.
- Gastcodes verwenden lokale Freigabeprofile und den technischen Token. Lokale Administratoren lesen innerhalb der Rechte des technischen Tokens.
- Downloads brauchen zusätzlich eine lokale Freigabe pro Benutzer oder Gastcode. PDF-Vorschau und Thumbnails bleiben unabhängig davon möglich.

## API und Oberfläche

- Die Benutzerverwaltung zeigt Paperless-Konto-ID und bestätigte E-Mail statt einer Profilauswahl. Benutzerkonten besitzen kein `profile_id`; Gastcodes haben weiterhin genau ein Profil.
- Die Sitzungsantwort enthält `has_access` und einen optionalen `access_error`. Fehlende Zuordnungen sperren den Dokumentzugriff, nicht die bereits bestätigte OIDC-Identität.
- Dokumentendpunkte liefern nur freigegebene Metadaten und Dateien. Fremde einzelne Dokumente erscheinen als nicht gefunden.
- OIDC-Filterkataloge werden ohne zusätzliche Objektberechtigungsprüfung über den technischen Token gelesen. Gastzugänge erhalten weiterhin profilabhängig eingeschränkte Vorschläge.
- Konfigurierbare Custom-Field-Suchfelder, CSRF-Prüfung, lokale Kontosperren und Sitzungslaufzeiten bleiben erhalten.

## Datenbank und Betrieb

- SQLAlchemy definiert das endgültige SQLite-Schema. `python -m searchbar.cli init-db` erstellt es bei einer Neuinstallation und verändert bei wiederholter Ausführung keine bestehenden Daten dieses Schemas.
- Keine Migrationen, alten Schemafassungen oder Datenübernahmepfade. Container und Entwicklungsumgebung verwenden denselben Initialisierungsbefehl.
- Der technische Paperless-Token braucht Benutzerleserechte für die Zuordnung und die bisherigen Katalog-/Dokumentrechte für Gastzugänge und lokale Administratoren.
- Paperless muss Remote-User für die API aktivieren. Der öffentliche Paperless-Proxy entfernt den Header aus externen Requests; der Backend-Port ist nicht öffentlich erreichbar. Die interne Verbindung ist nur vertrauenswürdigen Diensten zugänglich.
- Einrichtung und Prüfung der separat betriebenen Paperless-Instanz sind in der README beschrieben.

## Nachweise

Backendtests prüfen Zuordnung, aktuelle Rechte, fehlende Berechtigungen, Seitenzahlen, Dateiübertragung, getrennte parallele Benutzeranfragen und Gastzugänge. Initialisierungstests prüfen ein frisches Schema sowie wiederholten Start ohne Datenverlust. Browsertests prüfen automatische OIDC-Freigaben und die unabhängige Download-Freigabe. Die Prüfung mit echten Paperless-Konten und öffentlichem Proxy ergänzt diese isolierten Tests.
