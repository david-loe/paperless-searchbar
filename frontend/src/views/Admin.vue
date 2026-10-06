<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, errorMessage, refreshSession } from "../api";
import {
  emptyCatalog,
  emptyRules,
  type Profile,
  type User,
  type Code,
  type Catalog,
  type SearchSettings,
} from "../types";
import ChoiceSelect from "../components/ChoiceSelect.vue";
import CustomFilters from "../components/CustomFilters.vue";
const tab = ref("profiles"),
  catalog = ref(emptyCatalog()),
  profiles = ref<Profile[]>([]),
  users = ref<User[]>([]),
  codes = ref<Code[]>([]);
const searchSettings = ref<SearchSettings>({ custom_field_ids: [] });
const searchFieldChoices = computed(() => [
  ...catalog.value.custom_fields,
  ...searchSettings.value.custom_field_ids
    .filter(
      (id) => !catalog.value.custom_fields.some((field) => field.id === id),
    )
    .map((id) => ({ id, name: `Feld #${id} (nicht mehr verfügbar)` })),
]);
const error = ref(""),
  notice = ref(""),
  busy = ref(false),
  editing = ref(false),
  editingId = ref<number | null>(null),
  profileName = ref(""),
  rules = ref(emptyRules()),
  ids = ref("");
const codeName = ref(""),
  codeProfile = ref<number | null>(null),
  codeDownload = ref(false),
  duration = ref("86400"),
  expires = ref(""),
  newCode = ref("");
const profileLabel = (id: number | null) =>
  profiles.value.find((p) => p.id === id)?.name ?? "Keine Freigabe";
async function load() {
  [
    catalog.value,
    profiles.value,
    users.value,
    codes.value,
    searchSettings.value,
  ] = await Promise.all([
    api<Catalog>("/admin/filters"),
    api<Profile[]>("/admin/profiles"),
    api<User[]>("/admin/users"),
    api<Code[]>("/admin/codes"),
    api<SearchSettings>("/admin/search-settings"),
  ]);
}
onMounted(async () => {
  busy.value = true;
  try {
    await load();
  } catch (e) {
    error.value = errorMessage(e);
  } finally {
    busy.value = false;
  }
});
function edit(profile?: Profile) {
  editing.value = true;
  editingId.value = profile?.id ?? null;
  profileName.value = profile?.name ?? "";
  rules.value = profile
    ? JSON.parse(JSON.stringify(profile.rules))
    : emptyRules();
  ids.value = rules.value.document_ids.join(", ");
  error.value = "";
  notice.value = "";
}
async function action(fn: () => Promise<unknown>, message: string) {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    await fn();
    await load();
    notice.value = message;
  } catch (e) {
    error.value = errorMessage(e);
  } finally {
    busy.value = false;
  }
}
async function saveProfile() {
  await action(async () => {
    rules.value.document_ids = ids.value
      .split(",")
      .filter((v) => v.trim())
      .map(Number);
    const payload = {
      name: profileName.value,
      rules: rules.value.all_documents
        ? { ...emptyRules(), all_documents: true }
        : rules.value,
    };
    await api(
      "/admin/profiles" + (editingId.value ? `/${editingId.value}` : ""),
      payload,
      editingId.value ? "PUT" : "POST",
    );
    editing.value = false;
  }, "Freigabeprofil gespeichert.");
}
async function remove(profile: Profile) {
  if (confirm(`Profil „${profile.name}“ löschen?`))
    await action(
      () => api(`/admin/profiles/${profile.id}`, undefined, "DELETE"),
      "Profil gelöscht.",
    );
}
async function saveUser(user: User) {
  await action(async () => {
    await api(
      `/admin/users/${user.id}`,
      {
        active: user.active,
        is_admin: user.is_admin,
        allow_download: user.allow_download,
      },
      "PUT",
    );
    await refreshSession();
  }, "Benutzerrechte gespeichert.");
}
async function createCode() {
  newCode.value = "";
  await action(async () => {
    const expiry =
      duration.value === "custom"
        ? Math.floor(new Date(expires.value).getTime() / 1000)
        : Math.floor(Date.now() / 1000) + Number(duration.value);
    const result = await api<{ code: string }>("/admin/codes", {
      name: codeName.value,
      profile_id: codeProfile.value,
      allow_download: codeDownload.value,
      expires_at: expiry,
    });
    newCode.value = result.code;
    codeName.value = "";
    codeDownload.value = false;
  }, "Zugangscode erstellt.");
}
async function saveCodeDownload(code: Code, event: Event) {
  const input = event.target as HTMLInputElement;
  const allowDownload = input.checked;
  const previous = code.allow_download;
  code.allow_download = allowDownload;
  await action(
    () =>
      api(
        `/admin/codes/${code.id}`,
        { allow_download: allowDownload },
        "PATCH",
      ),
    "Download-Einstellung gespeichert.",
  );
  if (error.value) code.allow_download = previous;
}
async function revoke(code: Code) {
  if (confirm(`Zugang „${code.name}“ sofort widerrufen?`))
    await action(
      () => api(`/admin/codes/${code.id}/revoke`, {}),
      "Zugang widerrufen.",
    );
}
async function copy() {
  try {
    await navigator.clipboard.writeText(newCode.value);
    notice.value = "Code kopiert.";
  } catch {
    notice.value = "Code markieren und manuell kopieren.";
  }
}
</script>
<template>
  <p v-if="error" class="alert" role="alert">{{ error }}</p>
  <p v-if="notice" class="success" role="status">{{ notice }}</p>
  <div class="tabs" aria-label="Verwaltungsbereiche">
    <button
      v-for="item in [
        { id: 'search', name: 'Suchfelder' },
        { id: 'profiles', name: 'Freigabeprofile' },
        { id: 'users', name: 'Benutzer' },
        { id: 'codes', name: 'Zugangscodes' },
      ]"
      :key="item.id"
      :class="{ active: tab === item.id }"
      :aria-pressed="tab === item.id"
      @click="
        tab = item.id;
        newCode = '';
      "
    >
      {{ item.name }}
    </button>
  </div>
  <form
    v-if="tab === 'search'"
    class="card editor"
    @submit.prevent="
      action(
        () => api('/admin/search-settings', searchSettings, 'PUT'),
        'Suchfelder gespeichert.',
      )
    "
  >
    <p class="muted">
      Diese Felder erscheinen direkt in der Suche. Werte müssen exakt
      übereinstimmen.
    </p>
    <label v-for="field in searchFieldChoices" :key="field.id" class="check">
      <input
        v-model="searchSettings.custom_field_ids"
        type="checkbox"
        :value="field.id"
        :disabled="
          busy ||
          (searchSettings.custom_field_ids.length >= 8 &&
            !searchSettings.custom_field_ids.includes(field.id))
        "
      />
      {{ field.name }}
    </label>
    <p v-if="!catalog.custom_fields.length && !busy" class="muted">
      Keine Custom Fields vorhanden.
    </p>
    <div class="actions">
      <button class="primary" :disabled="busy">Suchfelder speichern</button
      ><span class="small muted"
        >{{ searchSettings.custom_field_ids.length }} von 8 Feldern</span
      >
    </div>
  </form>
  <section v-if="tab === 'profiles'">
    <div class="section-line">
      <h2>Freigabeprofile</h2>
      <button class="primary" @click="edit()">＋ Profil erstellen</button>
    </div>
    <form v-if="editing" class="card editor" @submit.prevent="saveProfile">
      <h2>{{ editingId ? "Profil bearbeiten" : "Neues Freigabeprofil" }}</h2>
      <label
        >Profilname<input
          v-model="profileName"
          maxlength="120"
          required
          placeholder="z. B. Buchhaltung Firma A" /></label
      ><label class="check"
        ><input v-model="rules.all_documents" type="checkbox" /> Alle Dokumente
        erlauben</label
      ><template v-if="!rules.all_documents"
        ><p class="muted small">
          Kriterien gelten zusammen (UND), mehrere Werte je Kriterium alternativ
          (ODER). Ohne Kriterien ist kein Dokument erlaubt.
        </p>
        <label
          >Dokument-IDs<input
            v-model="ids"
            placeholder="123, 456"
            pattern="\s*([1-9][0-9]*\s*(,\s*[1-9][0-9]*\s*)*)?"
            title="Positive IDs mit Komma trennen"
        /></label>
        <div class="two-columns">
          <ChoiceSelect
            v-model="rules.storage_paths"
            label="Erlaubte Speicherpfade"
            :choices="catalog.storage_paths"
            multiple
          /><ChoiceSelect
            v-model="rules.correspondents"
            label="Erlaubte Korrespondenten"
            :choices="catalog.correspondents"
            multiple
          />
        </div>
        <CustomFilters
          v-model="rules.custom_fields"
          :fields="catalog.custom_fields"
      /></template>
      <div class="actions">
        <button class="primary" :disabled="busy">Profil speichern</button
        ><button type="button" class="ghost" @click="editing = false">
          Abbrechen
        </button>
      </div>
    </form>
    <div v-if="!profiles.length && !busy" class="empty">
      Noch keine Profile. Erstelle dein erstes Freigabeprofil.
    </div>
    <div class="profile-grid">
      <article v-for="p in profiles" :key="p.id" class="card profile-card">
        <span class="badge">{{
          p.rules.all_documents ? "Alle Dokumente" : "Eingeschränkte Freigabe"
        }}</span>
        <h3>{{ p.name }}</h3>
        <p v-if="p.error" class="alert">{{ p.error }}</p>
        <p v-else class="muted small">
          {{
            p.rules.all_documents
              ? "Vollständiger Lesezugriff."
              : `${p.rules.document_ids.length} Dokument-IDs · ${p.rules.storage_paths.length} Speicherpfade · ${p.rules.correspondents.length} Korrespondenten · ${p.rules.custom_fields.length} Feldfilter`
          }}
        </p>
        <div class="actions">
          <button class="secondary" @click="edit(p)">Bearbeiten</button
          ><button class="ghost danger" :disabled="busy" @click="remove(p)">
            Löschen
          </button>
        </div>
      </article>
    </div>
  </section>
  <section v-if="tab === 'users'">
    <h2>Benutzer und Freigaben</h2>
    <p class="muted">
      OIDC-Benutzer erhalten ihre Dokumentrechte aus Paperless. Die Zuordnung
      erfolgt über ihre bestätigte E-Mail-Adresse.
    </p>
    <article v-for="user in users" :key="user.id" class="card user-card">
      <div>
        <h3>{{ user.name }}</h3>
        <p class="small muted">
          {{
            user.local
              ? "Lokaler Administrator"
              : `${user.issuer} · ${user.subject}`
          }}
        </p>
      </div>
      <form class="user-controls" @submit.prevent="saveUser(user)">
        <p v-if="!user.local" class="small muted">
          {{ user.verified_email || "Keine bestätigte E-Mail-Adresse" }} ·
          {{
            user.paperless_user_id
              ? `Paperless-Konto #${user.paperless_user_id}`
              : "Keine Paperless-Zuordnung"
          }}
          <span v-if="user.paperless_link_error">{{
            user.paperless_link_error
          }}</span>
        </p>
        <label class="check"
          ><input v-model="user.allow_download" type="checkbox" />Download
          erlauben</label
        >
        <label class="check"
          ><input v-model="user.active" type="checkbox" /> Aktiv</label
        ><label class="check"
          ><input
            v-model="user.is_admin"
            type="checkbox"
            :disabled="user.local"
          />
          Administrator</label
        ><button class="primary" :disabled="busy">Benutzer speichern</button>
      </form>
    </article>
  </section>
  <section v-if="tab === 'codes'">
    <h2>Zeitlich begrenzte Zugänge</h2>
    <form class="card editor" @submit.prevent="createCode">
      <div class="search-grid">
        <label
          >Bezeichnung<input
            v-model="codeName"
            required
            maxlength="120"
            placeholder="z. B. Steuerberatung"
        /></label>
        <ChoiceSelect
          v-model="codeProfile"
          label="Freigabeprofil"
          :choices="profiles"
          required
          empty-label="Profil auswählen"
        />
        <label
          >Gültigkeit<select v-model="duration">
            <option value="3600">1 Stunde</option>
            <option value="86400">24 Stunden</option>
            <option value="604800">7 Tage</option>
            <option value="custom">Individueller Ablauf</option>
          </select></label
        ><label v-if="duration === 'custom'"
          >Gültig bis (Ortszeit)<input
            v-model="expires"
            type="datetime-local"
            required
        /></label>
      </div>
      <label class="check"
        ><input v-model="codeDownload" type="checkbox" />Download
        erlauben</label
      >
      <button class="primary" :disabled="busy">Zugangscode erstellen</button>
    </form>
    <div v-if="newCode" class="success code-reveal">
      <strong>Jetzt kopieren — der Code wird nur einmal angezeigt.</strong
      ><code>{{ newCode }}</code
      ><button class="secondary" @click="copy">Code kopieren</button
      ><button class="ghost" @click="newCode = ''">Schließen</button>
    </div>
    <div class="card table-wrap">
      <table>
        <thead>
          <tr>
            <th>Bezeichnung</th>
            <th>Freigabe</th>
            <th>Gültig bis</th>
            <th>Status</th>
            <th>Download</th>
            <th>Aktion</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="code in codes" :key="code.id">
            <td>{{ code.name }}</td>
            <td>{{ profileLabel(code.profile_id) }}</td>
            <td>
              {{ new Date(code.expires_at * 1000).toLocaleString("de-DE") }}
            </td>
            <td>
              <span class="badge">{{
                code.revoked
                  ? "Widerrufen"
                  : code.expires_at * 1000 <= Date.now()
                    ? "Abgelaufen"
                    : "Aktiv"
              }}</span>
            </td>
            <td>
              <input
                type="checkbox"
                :checked="code.allow_download"
                :disabled="busy"
                :aria-label="`Download für ${code.name} erlauben`"
                @change="saveCodeDownload(code, $event)"
              />
            </td>
            <td>
              <button
                v-if="!code.revoked && code.expires_at * 1000 > Date.now()"
                class="ghost danger"
                :disabled="busy"
                @click="revoke(code)"
              >
                Widerrufen
              </button>
            </td>
          </tr>
          <tr v-if="!codes.length">
            <td colspan="6">Noch keine Zugangscodes erstellt.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
  <p v-if="busy" role="status" class="muted">Wird verarbeitet …</p>
</template>
