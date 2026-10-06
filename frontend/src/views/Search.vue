<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api, errorMessage, session } from "../api";
import { emptyCatalog, type CustomFilter, type Document } from "../types";
import ChoiceSelect from "../components/ChoiceSelect.vue";
import SearchFields from "../components/SearchFields.vue";
import SearchResult from "../components/SearchResult.vue";
const router = useRouter();
const catalog = ref(emptyCatalog()),
  documentId = ref(""),
  storagePath = ref<number | number[] | null>(null),
  correspondent = ref<number | number[] | null>(null),
  documentType = ref<number | number[] | null>(null);
const custom = ref<CustomFilter[]>([]),
  results = ref<Document[]>([]),
  count = ref(0),
  page = ref(1),
  searched = ref(false),
  busy = ref(false),
  loading = ref(true),
  error = ref("");
const hasCriteria = computed(() =>
  Boolean(
    documentId.value ||
    storagePath.value ||
    correspondent.value ||
    documentType.value ||
    custom.value.length,
  ),
);
// Pagination uses the submitted criteria even if the form has since been edited.
let submitted: Record<string, unknown> = {};
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
async function search(next?: number) {
  if (busy.value) return;
  if (next === undefined) {
    submitted = {
      document_id: documentId.value ? Number(documentId.value) : null,
      storage_path: storagePath.value,
      correspondent: correspondent.value,
      document_type: documentType.value,
      custom_fields: JSON.parse(JSON.stringify(custom.value)),
    };
  }
  busy.value = true;
  error.value = "";
  results.value = [];
  count.value = 0;
  page.value = next ?? 1;
  try {
    const data = await api<{ count: number; results: Document[] }>(
      "/documents/search",
      { ...submitted, page: page.value },
    );
    if (
      submitted.document_id &&
      data.results[0]?.id === submitted.document_id
    ) {
      await router.push(`/documents/${data.results[0].id}`);
      return;
    }
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
  documentId.value = "";
  storagePath.value = null;
  correspondent.value = null;
  documentType.value = null;
  custom.value = [];
  results.value = [];
  count.value = 0;
  searched.value = false;
  error.value = "";
}
</script>
<template>
  <div class="search-page" :class="{ 'has-results': searched }">
    <p v-if="!session?.has_access" class="empty" role="status">
      {{ session?.access_error || "Dein Zugang wartet auf Freigabe." }}
    </p>
    <template v-else>
      <form
        role="search"
        aria-label="Dokumente suchen"
        @submit.prevent="search()"
      >
        <div class="search-bar">
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
          >
            <circle cx="10.5" cy="10.5" r="6.5" />
            <path d="m16 16 4.5 4.5" />
          </svg>
          <input
            v-model="documentId"
            aria-label="Dokument-ID"
            type="text"
            inputmode="numeric"
            pattern="[0-9]*[1-9][0-9]*"
            placeholder="Dokument-ID eingeben"
            autocomplete="off"
          />
          <button
            type="submit"
            class="primary"
            :disabled="busy || loading || !hasCriteria"
          >
            {{ busy ? "Sucht …" : "Suchen" }}
          </button>
        </div>
        <fieldset
          class="search-filters"
          :disabled="busy || loading"
          aria-label="Suchfilter"
        >
          <ChoiceSelect
            v-model="storagePath"
            label="Speicherpfad"
            :choices="catalog.storage_paths"
          />
          <ChoiceSelect
            v-model="correspondent"
            label="Korrespondent"
            :choices="catalog.correspondents"
          />
          <ChoiceSelect
            v-model="documentType"
            label="Dokumenttyp"
            :choices="catalog.document_types"
          />
          <SearchFields v-model="custom" :fields="catalog.custom_fields" />
        </fieldset>
        <div class="search-status">
          <span v-if="loading" class="small muted" role="status"
            >Filter werden geladen …</span
          >
          <button
            v-if="hasCriteria || searched"
            type="button"
            class="ghost"
            :disabled="busy"
            @click="reset"
          >
            Zurücksetzen
          </button>
        </div>
      </form>
      <p v-if="error" class="alert" role="alert">{{ error }}</p>
      <section
        v-if="searched || busy"
        class="results"
        aria-label="Suchergebnisse"
        :aria-busy="busy"
      >
        <p class="small muted" role="status">
          {{
            busy
              ? "Dokumente werden gesucht …"
              : count
                ? `${count} Dokument${count === 1 ? "" : "e"}`
                : "Keine passenden Dokumente."
          }}
        </p>
        <div class="result-list">
          <SearchResult
            v-for="doc in results"
            :key="doc.id"
            :document="doc"
            :fields="catalog.custom_fields"
          />
        </div>
        <div v-if="count > 25" class="pagination">
          <button
            class="secondary"
            :disabled="page === 1 || busy"
            @click="search(page - 1)"
          >
            Zurück
          </button>
          <span>Seite {{ page }} von {{ Math.ceil(count / 25) }}</span>
          <button
            class="secondary"
            :disabled="page * 25 >= count || busy"
            @click="search(page + 1)"
          >
            Weiter
          </button>
        </div>
      </section>
    </template>
  </div>
</template>
