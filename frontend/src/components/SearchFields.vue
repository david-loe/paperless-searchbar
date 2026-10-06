<script setup lang="ts">
import { ref, watch } from "vue";
import type { CustomField, CustomFilter } from "../types";
import SearchableSelect from "./SearchableSelect.vue";
defineProps<{ fields: CustomField[] }>();
const model = defineModel<CustomFilter[]>({ required: true });
const drafts = ref<Record<number, string>>({});
watch(model, (filters) => {
  for (const id of Object.keys(drafts.value)) {
    if (!filters.some((filter) => filter.field === Number(id)))
      delete drafts.value[Number(id)];
  }
});
function value(field: CustomField) {
  if (drafts.value[field.id] !== undefined) return drafts.value[field.id];
  const current = model.value.find(
    (filter) => filter.field === field.id,
  )?.value;
  return Array.isArray(current) ? current.join(", ") : (current ?? "");
}
function update(field: CustomField, event: Event) {
  const raw = (event.target as HTMLInputElement).value;
  drafts.value[field.id] = raw;
  let next: unknown = raw;
  if (field.data_type === "boolean") next = raw === "true";
  else if (["integer", "float"].includes(field.data_type)) next = Number(raw);
  else if (field.data_type === "documentlink")
    next = raw.split(",").map((id) => Number(id.trim()));
  setValue(field, raw === "" ? null : next);
}
function setValue(field: CustomField, next: unknown) {
  const remaining = model.value.filter((filter) => filter.field !== field.id);
  model.value =
    next === null
      ? remaining
      : [...remaining, { field: field.id, op: "exact", value: next }];
}
</script>
<template>
  <template v-for="field in fields" :key="field.id">
    <SearchableSelect
      v-if="field.data_type === 'select'"
      :label="field.name"
      :choices="
        field.options.map((option) => ({ id: option.id, name: option.label }))
      "
      :model-value="
        (model.find((filter) => filter.field === field.id)?.value as
          string | undefined) ?? null
      "
      @update:model-value="setValue(field, $event)"
    />
    <label v-else
      >{{ field.name }}
      <select
        v-if="field.data_type === 'boolean'"
        :value="String(value(field))"
        @change="update(field, $event)"
      >
        <option value="">Alle</option>
        <option value="true">Ja</option>
        <option value="false">Nein</option>
      </select>
      <input
        v-else
        :type="
          field.data_type === 'date'
            ? 'date'
            : ['integer', 'float', 'monetary'].includes(field.data_type)
              ? 'number'
              : 'text'
        "
        :step="field.data_type === 'integer' ? '1' : 'any'"
        :value="value(field)"
        :placeholder="
          field.data_type === 'documentlink'
            ? 'Dokument-IDs, z. B. 123, 456'
            : field.name
        "
        :pattern="
          field.data_type === 'documentlink'
            ? '\\s*[1-9][0-9]*\\s*(,\\s*[1-9][0-9]*\\s*)*'
            : undefined
        "
        :maxlength="2000"
        @input="update(field, $event)"
      />
    </label>
  </template>
</template>
