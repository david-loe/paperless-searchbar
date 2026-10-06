<script setup lang="ts">
import { computed, ref } from "vue";
import type { CustomField, Document } from "../types";
import { displayValue, displayDate } from "../format";
const props = defineProps<{ document: Document; fields: CustomField[] }>();
const thumbnailFailed = ref(false);
const metadata = computed(() => [
  { name: "Dokument-ID", value: `#${props.document.id}` },
  { name: "Datum", value: displayDate(props.document.created) },
  { name: "Dokumenttyp", value: displayValue(props.document.document_type) },
  { name: "Korrespondent", value: displayValue(props.document.correspondent) },
  { name: "Speicherpfad", value: displayValue(props.document.storage_path) },
]);
const custom = computed(() =>
  props.fields.map((field) => ({
    id: field.id,
    name: field.name,
    value: displayValue(
      props.document.custom_fields.find((item) => item.field === field.id)
        ?.value,
      field.data_type,
    ),
  })),
);
</script>
<template>
  <RouterLink :to="`/documents/${document.id}`" class="result-row">
    <div class="result-thumbnail">
      <img
        v-if="!thumbnailFailed"
        :src="`/api/documents/${document.id}/thumb`"
        :alt="`Vorschau: ${document.title}`"
        width="56"
        height="74"
        loading="lazy"
        decoding="async"
        @error="thumbnailFailed = true"
      />
      <span
        v-else
        class="thumbnail-placeholder"
        role="img"
        aria-label="Keine Miniaturansicht verfügbar"
      >
        <svg
          viewBox="0 0 32 40"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          aria-hidden="true"
        >
          <path d="M6 2h13l8 8v28H6zM19 2v9h8M11 19h11M11 25h11M11 31h7" />
        </svg>
      </span>
    </div>
    <h3>{{ document.title || "Ohne Titel" }}</h3>
    <dl class="result-metadata">
      <div v-for="item in metadata" :key="item.name">
        <dt>{{ item.name }}</dt>
        <dd>{{ item.value }}</dd>
      </div>
    </dl>
    <dl v-if="custom.length" class="result-metadata result-custom">
      <div v-for="item in custom" :key="item.id">
        <dt>{{ item.name }}</dt>
        <dd class="result-custom-value">{{ item.value }}</dd>
      </div>
    </dl>
  </RouterLink>
</template>
