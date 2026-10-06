<script setup lang="ts">
import { defineAsyncComponent, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api, errorMessage, session } from "../api";
import type { Document } from "../types";
const PdfPreview = defineAsyncComponent(
  () => import("../components/PdfPreview.vue"),
);
import { displayValue as display, displayDate } from "../format";
const id = String(useRoute().params.id),
  doc = ref<Document | null>(null),
  error = ref(""),
  preview = ref(""),
  loading = ref(true);
let timer: ReturnType<typeof setInterval> | undefined;
let alive = true;
let checking = false;
async function check() {
  if (checking || !alive) return;
  checking = true;
  try {
    const result = await api<Document>(`/documents/${id}`);
    if (alive) doc.value = result;
  } catch (e) {
    if (alive) {
      doc.value = null;
      preview.value = "";
      error.value = errorMessage(e);
    }
  } finally {
    checking = false;
  }
}
onMounted(async () => {
  await check();
  if (!alive) return;
  loading.value = false;
  if (doc.value) {
    try {
      const r = await fetch(`/api/documents/${id}/preview`, {
        headers: { Range: "bytes=0-0" },
        cache: "no-store",
      });
      const pdf =
        r.ok && r.headers.get("content-type")?.includes("application/pdf");
      await r.body?.cancel();
      if (alive && pdf) preview.value = `/api/documents/${id}/preview`;
      if (r.status === 401 || r.status === 403 || r.status === 404)
        await check();
    } catch {
      // Show the fallback if the preview cannot be loaded.
    }
  }
  if (!alive) return;
  timer = setInterval(check, 30000);
});
onUnmounted(() => {
  alive = false;
  clearInterval(timer);
});
</script>
<template>
  <RouterLink class="back-link" to="/">← Zur Suche</RouterLink>
  <p v-if="error" class="alert" role="alert">{{ error }}</p>
  <p v-if="loading" role="status">Dokument wird geladen …</p>
  <template v-if="doc"
    ><section class="page-heading document-heading">
      <div>
        <p class="eyebrow">DOKUMENT #{{ doc.id }}</p>
        <h1>{{ doc.title }}</h1>
      </div>
      <div class="actions">
        <a
          v-if="session?.allow_download"
          class="button secondary"
          :href="`/api/documents/${doc.id}/download`"
          >Herunterladen ↓</a
        ><a
          class="button primary"
          :href="doc.paperless_url"
          target="_blank"
          rel="noopener noreferrer"
          >In Paperless bearbeiten ↗</a
        >
      </div>
    </section>
    <div class="document-layout">
      <aside class="card">
        <h2>Dokumentdetails</h2>
        <dl>
          <dt>Datum</dt>
          <dd>{{ displayDate(doc.created) }}</dd>
          <dt>Dokumenttyp</dt>
          <dd>{{ doc.document_type || "—" }}</dd>
          <dt>Korrespondent</dt>
          <dd>{{ doc.correspondent || "—" }}</dd>
          <dt>Speicherpfad</dt>
          <dd>{{ doc.storage_path || "—" }}</dd>
          <template v-for="field in doc.custom_fields" :key="field.field"
            ><dt>{{ field.name }}</dt>
            <dd>{{ display(field.value) }}</dd></template
          >
        </dl>
      </aside>
      <div class="card preview">
        <PdfPreview v-if="preview" :url="preview" />
        <div v-else class="empty">
          <h2>Keine PDF-Vorschau verfügbar</h2>
          <p v-if="session?.allow_download">
            Du kannst die Datei herunterladen und auf deinem Gerät öffnen.
          </p>
        </div>
      </div>
    </div></template
  >
</template>
