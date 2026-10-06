<script setup lang="ts">
import type { CustomField, CustomFilter } from "../types";
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
function options(f: CustomFilter, event: Event) {
  f.value = Array.from((event.target as HTMLSelectElement).selectedOptions).map(
    (o) => o.value,
  );
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
      <label
        >Feld<select v-model="filter.field" @change="changeField(filter)">
          <option v-for="f in fields" :key="f.id" :value="f.id">
            {{ f.name }}
          </option>
        </select></label
      >
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
      <label
        v-else-if="
          filter.op !== 'empty' && field(filter)?.data_type === 'select'
        "
        >Wert<select
          v-if="filter.op === 'in'"
          multiple
          :value="filter.value"
          required
          @change="options(filter, $event)"
        >
          <option v-for="o in field(filter)?.options" :key="o.id" :value="o.id">
            {{ o.label }}
          </option></select
        ><select v-else v-model="filter.value" required>
          <option value="" disabled>Wählen …</option>
          <option v-for="o in field(filter)?.options" :key="o.id" :value="o.id">
            {{ o.label }}
          </option>
        </select></label
      >
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
