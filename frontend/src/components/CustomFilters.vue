<script setup lang="ts">
import type { CustomField, CustomFilter } from "../types";
import ChoiceSelect from "./ChoiceSelect.vue";
import SearchableSelect from "./SearchableSelect.vue";
const props = defineProps<{ fields: CustomField[] }>();
const model = defineModel<CustomFilter[]>({ required: true });
const labels: Record<string, string> = {
  exact: "ist gleich",
  icontains: "enthält",
  range: "liegt zwischen",
  in: "ist einer von",
  contains: "verknüpft mit",
  exists: "ist vorhanden",
  empty: "ist leer",
};
const field = (f: CustomFilter) => props.fields.find((v) => v.id === f.field);
function initial(f: CustomFilter) {
  const kind = field(f)?.data_type;
  if (f.op === "empty") f.value = null;
  else if (f.op === "exists" || kind === "boolean")
    f.value = f.op === "in" ? [true] : true;
  else if (f.op === "range") f.value = ["", ""];
  else if (f.op === "in" || kind === "documentlink") f.value = [];
  else f.value = "";
}
function changeField(f: CustomFilter) {
  f.op = "exact";
  initial(f);
}
function add() {
  const first = props.fields[0];
  if (first) {
    const f = { field: first.id, op: "exact", value: null } as CustomFilter;
    initial(f);
    model.value = [...model.value, f];
  }
}
function updateValue(f: CustomFilter, e: Event, index?: number) {
  const text = (e.target as HTMLInputElement).value;
  const kind = field(f)?.data_type;
  const scalar = (v: string) =>
    kind === "integer" || kind === "float"
      ? v === ""
        ? ""
        : Number(v)
      : kind === "boolean"
        ? v === "true"
        : v.trim();
  if (index !== undefined) {
    const next = [...(f.value as unknown[])];
    next[index] = scalar(text);
    f.value = next;
  } else if (kind === "documentlink")
    f.value = text
      .split(",")
      .filter((x) => x.trim())
      .map(Number);
  else if (f.op === "in")
    f.value = text
      .split(",")
      .filter((x) => x.trim())
      .map(scalar);
  else f.value = scalar(text);
}
const inputType = (f: CustomFilter) =>
  field(f)?.data_type === "date"
    ? "date"
    : ["integer", "float", "monetary"].includes(field(f)?.data_type ?? "")
      ? "number"
      : "text";
</script>
<template>
  <div class="custom-filters">
    <fieldset v-for="(filter, index) in model" :key="index" class="filter-row">
      <legend>Custom Field {{ index + 1 }}</legend>
      <ChoiceSelect
        :model-value="filter.field"
        label="Feld"
        :choices="fields"
        required
        @update:model-value="
          filter.field = $event as number;
          changeField(filter);
        "
      />
      <label
        >Bedingung<select v-model="filter.op" @change="initial(filter)">
          <option v-for="op in field(filter)?.operators" :key="op" :value="op">
            {{ labels[op] }}
          </option>
        </select></label
      >
      <label v-if="filter.op === 'exists'"
        >Wert<select v-model="filter.value">
          <option :value="true">Ja</option>
          <option :value="false">Nein</option>
        </select></label
      >
      <template v-else-if="filter.op === 'range'"
        ><label
          >Von<input
            :type="inputType(filter)"
            step="any"
            :value="(filter.value as unknown[])[0]"
            required
            @input="updateValue(filter, $event, 0)" /></label
        ><label
          >Bis<input
            :type="inputType(filter)"
            step="any"
            :value="(filter.value as unknown[])[1]"
            required
            @input="updateValue(filter, $event, 1)" /></label
      ></template>
      <SearchableSelect
        v-else-if="
          filter.op !== 'empty' && field(filter)?.data_type === 'select'
        "
        label="Wert"
        :choices="
          (field(filter)?.options ?? []).map((option) => ({
            id: option.id,
            name: option.label,
          }))
        "
        :model-value="filter.value as string | string[] | null"
        :multiple="filter.op === 'in'"
        required
        empty-label="Wählen …"
        @update:model-value="filter.value = $event"
      />
      <label
        v-else-if="
          filter.op !== 'empty' && field(filter)?.data_type === 'boolean'
        "
        >Wert<select v-model="filter.value" :multiple="filter.op === 'in'">
          <option :value="true">Ja</option>
          <option :value="false">Nein</option>
        </select></label
      >
      <label v-else-if="filter.op !== 'empty'"
        >{{
          filter.op === "in" || field(filter)?.data_type === "documentlink"
            ? "Werte, mit Komma getrennt"
            : "Wert"
        }}<input
          :type="
            filter.op === 'in' || field(filter)?.data_type === 'documentlink'
              ? 'text'
              : inputType(filter)
          "
          step="any"
          :value="
            Array.isArray(filter.value) ? filter.value.join(', ') : filter.value
          "
          required
          @input="updateValue(filter, $event)"
      /></label>
      <button
        type="button"
        class="ghost remove"
        :aria-label="`Custom Field ${index + 1} entfernen`"
        @click="model = model.filter((_, i) => i !== index)"
      >
        Entfernen
      </button>
    </fieldset>
    <button
      type="button"
      class="secondary"
      :disabled="!fields.length || model.length >= 8"
      @click="add"
    >
      ＋ Custom Field hinzufügen
    </button>
  </div>
</template>
