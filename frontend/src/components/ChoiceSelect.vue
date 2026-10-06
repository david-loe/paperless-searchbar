<script setup lang="ts">
import { computed, ref, useId } from "vue";
import type { Choice } from "../types";
const props = defineProps<{
  label: string;
  choices: Choice[];
  multiple?: boolean;
}>();
const model = defineModel<number | number[] | null>();
const query = ref("");
const id = useId();
const filtered = computed(() =>
  props.choices.filter(
    (c) =>
      c.name.toLocaleLowerCase().includes(query.value.toLocaleLowerCase()) ||
      (Array.isArray(model.value)
        ? model.value.includes(c.id)
        : model.value === c.id),
  ),
);
function change(event: Event) {
  const select = event.target as HTMLSelectElement;
  model.value = props.multiple
    ? Array.from(select.selectedOptions).map((o) => Number(o.value))
    : select.value
      ? Number(select.value)
      : null;
}
</script>
<template>
  <div class="field">
    <label :for="id">{{ label }}</label
    ><input
      v-model="query"
      type="search"
      :aria-label="`${label} filtern`"
      placeholder="Auswahl filtern …"
    /><select :id="id" :multiple="multiple" :value="model" @change="change">
      <option v-if="!multiple" value="">Alle</option>
      <option v-for="choice in filtered" :key="choice.id" :value="choice.id">
        {{ choice.name }}
      </option></select
    ><small v-if="multiple">Mehrere Werte mit Strg/Cmd auswählen.</small>
  </div>
</template>
