<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, errorMessage, session } from "../api";
import { emptyCatalog, type CustomFilter, type Document } from "../types";
import ChoiceSelect from "../components/ChoiceSelect.vue";
import CustomFilters from "../components/CustomFilters.vue";
const catalog = ref(emptyCatalog()),
  documentId = ref<number | null>(null),
  storagePath = ref<number | number[] | null>(null),
  correspondent = ref<number | number[] | null>(null);
const custom = ref<CustomFilter[]>([]),
  results = ref<Document[]>([]),
  count = ref(0),
  page = ref(1),
  searched = ref(false),
  busy = ref(false),
  loading = ref(true),
  error = ref("");
onMounted(async () => {
  if (!session.value?.has_access) {
    loading.value = false;
    return;
  }
  try {
    catalog.value = await api("/filters");
  } catch (e) {
    error.value = errorMessage(e);
  } finally {
    loading.value = false;
  }
});
async function search(next = 1) {
  busy.value = true;
  error.value = "";
  results.value = [];
  count.value = 0;
  page.value = next;
  try {
    const data = await api<{ count: number; results: Document[] }>(
      "/documents/search",
      {
        document_id: documentId.value || null,
        storage_path: storagePath.value,
        correspondent: correspondent.value,
        custom_fields: custom.value,
        page: next,
      },
    );
    results.value = data.results;
    count.value = data.count;
    searched.value = true;
  } catch (e) {
    error.value = errorMessage(e);
  } finally {
    busy.value = false;
  }
}
function reset() {
  documentId.value = null;
  storagePath.value = null;
  correspondent.value = null;
  custom.value = [];
  results.value = [];
  count.value = 0;
  searched.value = false;
  error.value = "";
}
</script>
<template>
  <section class="page-heading">
    <p class="eyebrow">DOKUMENTE ENTDECKEN</p>
    <h1>Was möchtest du finden?</h1>
    <p class="muted">
      Suche gezielt nach einer Dokument-ID oder kombiniere passende Filter.
    </p>
  </section>
  <div v-if="!session?.has_access" class="card empty">
    <h2>Dein Zugang wartet auf Freigabe</h2>
    <p>Ein Administrator muss dir zunächst ein Freigabeprofil zuweisen.</p>
  </div>
  <template v-else
    ><p v-if="error" class="alert" role="alert">{{ error }}</p>
    <form class="card search-card" @submit.prevent="search()">
      <div class="section-line">
        <h2>Suche eingrenzen</h2>
        <span class="badge">Nur freigegebene Dokumente</span>
      </div>
      <p v-if="loading" role="status">Filter werden geladen …</p>
      <div class="search-grid">
        <label
          >Dokument-ID<input
            v-model.number="documentId"
            aria-label="Dokument-ID"
            aria-describedby="document-id-help"
            type="number"
            min="1"
            step="1"
            placeholder="z. B. 123"
          /><small id="document-id-help"
            >Die interne ID aus Paperless.</small
          ></label
        ><ChoiceSelect
          v-model="storagePath"
          label="Speicherpfad"
          :choices="catalog.storage_paths"
        /><ChoiceSelect
          v-model="correspondent"
          label="Korrespondent"
          :choices="catalog.correspondents"
        />
      </div>
      <CustomFilters v-model="custom" :fields="catalog.custom_fields" />
      <div class="form-footer">
        <span class="small muted"
          >Alle gesetzten Kriterien müssen zutreffen.</span
        >
        <div class="actions">
          <button type="button" class="ghost" @click="reset">
            Zurücksetzen</button
          ><button class="primary" :disabled="busy || loading">
            {{ busy ? "Suche läuft …" : "Dokumente suchen" }}
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </div>
    </form>
    <section class="results">
      <div class="section-line">
        <h2>
          {{
            searched
              ? `${count} Dokument${count === 1 ? "" : "e"} gefunden`
              : "Deine Ergebnisse"
          }}
        </h2>
        <span v-if="searched && count" class="small muted"
          >Neueste ID zuerst</span
        >
      </div>
      <div v-if="!results.length" class="empty">
        <span class="empty-icon" aria-hidden="true">⌕</span>
        <h3>
          {{
            busy
              ? "Dokumente werden gesucht …"
              : searched
                ? "Keine passenden Dokumente"
                : "Deine Suche beginnt hier"
          }}
        </h3>
        <p class="muted">
          {{
            searched
              ? "Passe die Filter an und versuche es erneut."
              : "Gib eine Dokument-ID ein oder wähle einen Filter aus."
          }}
        </p>
      </div>
      <div v-else class="result-list">
        <RouterLink
          v-for="doc in results"
          :key="doc.id"
          :to="`/documents/${doc.id}`"
          class="result-row"
          ><span class="document-icon" aria-hidden="true">▤</span>
          <div>
            <span class="small muted"
              >#{{ doc.id }} ·
              {{ doc.created?.slice(0, 10) || "Ohne Datum" }}</span
            >
            <h3>{{ doc.title }}</h3>
            <p>
              {{ doc.correspondent || "Ohne Korrespondent" }}
              <span v-if="doc.storage_path">· {{ doc.storage_path }}</span>
            </p>
          </div>
          <span class="arrow" aria-hidden="true">↗</span></RouterLink
        >
      </div>
      <div v-if="count > 25" class="pagination">
        <button
          class="secondary"
          :disabled="page === 1 || busy"
          @click="search(page - 1)"
        >
          Zurück</button
        ><span>Seite {{ page }} von {{ Math.ceil(count / 25) }}</span
        ><button
          class="secondary"
          :disabled="page * 25 >= count || busy"
          @click="search(page + 1)"
        >
          Weiter
        </button>
      </div>
    </section></template
  >
</template>
