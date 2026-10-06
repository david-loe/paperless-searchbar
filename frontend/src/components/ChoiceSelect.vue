<script setup lang="ts">
import type { Choice } from "../types";
import SearchableSelect from "./SearchableSelect.vue";
defineProps<{
  label: string;
  choices: Choice[];
  multiple?: boolean;
  required?: boolean;
  disabled?: boolean;
  emptyLabel?: string;
}>();
const model = defineModel<number | number[] | null>();
</script>
<template>
  <SearchableSelect
    v-model="model"
    :label="label"
    :choices="choices"
    :multiple="multiple"
    :required="required"
    :disabled="disabled"
    :empty-label="emptyLabel ?? (multiple ? 'Keine ausgewählt' : 'Alle')"
  />
</template>
