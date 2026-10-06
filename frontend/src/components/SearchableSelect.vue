<script setup lang="ts" generic="T extends string | number">
import {
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  ref,
  useId,
  watch,
} from "vue";
const props = withDefaults(
  defineProps<{
    label: string;
    choices: { id: T; name: string }[];
    multiple?: boolean;
    required?: boolean;
    disabled?: boolean;
    emptyLabel?: string;
  }>(),
  { emptyLabel: "Alle" },
);
const model = defineModel<T | T[] | null>();
const id = useId();
const root = ref<HTMLElement>(),
  trigger = ref<HTMLButtonElement>(),
  searchInput = ref<HTMLInputElement>();
const opened = ref(false),
  query = ref(""),
  active = ref(0),
  invalid = ref(false);
const selected = (value: T | null) =>
  Array.isArray(model.value)
    ? model.value.includes(value as T)
    : (model.value ?? null) === value;
const options = computed<{ id: T | null; name: string }[]>(() => {
  const text = query.value.trim().toLocaleLowerCase("de");
  const choices = props.choices.filter((choice) =>
    choice.name.toLocaleLowerCase("de").includes(text),
  );
  return !props.multiple && !props.required && !text
    ? [{ id: null, name: props.emptyLabel }, ...choices]
    : choices;
});
const summary = computed(() => {
  const names = props.choices
    .filter((choice) => selected(choice.id))
    .map((choice) => choice.name);
  return names.length ? names.join(", ") : props.emptyLabel;
});
const activeId = computed(() =>
  options.value[active.value] ? `${id}-option-${active.value}` : undefined,
);
async function show() {
  if (props.disabled || trigger.value?.matches(":disabled")) return;
  query.value = "";
  opened.value = true;
  await nextTick();
  active.value = Math.max(
    0,
    options.value.findIndex((choice) => selected(choice.id)),
  );
  searchInput.value?.focus();
  scrollActive();
}
function close(focus = false) {
  opened.value = false;
  if (focus) trigger.value?.focus();
}
function pick(value: T | null) {
  if (props.disabled || trigger.value?.matches(":disabled")) return;
  if (props.multiple && value !== null) {
    const values = Array.isArray(model.value) ? model.value : [];
    model.value = values.includes(value)
      ? values.filter((item) => item !== value)
      : [...values, value];
  } else {
    model.value = value;
    close(true);
  }
  invalid.value = false;
}
function scrollActive() {
  void nextTick(() => {
    if (activeId.value)
      document
        .getElementById(activeId.value)
        ?.scrollIntoView?.({ block: "nearest" });
  });
}
function keydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    event.preventDefault();
    close(true);
  } else if (event.key === "Tab") {
    // Let native focus navigation finish before removing the focused input.
    setTimeout(() => close(), 0);
  } else if (["ArrowDown", "ArrowUp"].includes(event.key)) {
    event.preventDefault();
    const count = options.value.length;
    if (count)
      active.value =
        (active.value + (event.key === "ArrowDown" ? 1 : -1) + count) % count;
    scrollActive();
  } else if (event.key === "Enter") {
    event.preventDefault();
    const option = options.value[active.value];
    if (option) pick(option.id);
  }
}
function outside(event: Event) {
  if (
    opened.value &&
    event.target instanceof Node &&
    !root.value?.contains(event.target)
  )
    close();
}
watch(query, () => {
  active.value = 0;
  scrollActive();
});
watch(model, () => {
  invalid.value = false;
});
watch(
  () => props.disabled,
  (value) => {
    if (value) close();
  },
);
onMounted(() => {
  document.addEventListener("pointerdown", outside);
  document.addEventListener("focusin", outside);
});
onUnmounted(() => {
  document.removeEventListener("pointerdown", outside);
  document.removeEventListener("focusin", outside);
});
</script>
<template>
  <div ref="root" class="field searchable-select">
    <label :id="`${id}-label`" :for="id">{{ label }}</label>
    <button
      ref="trigger"
      :id="id"
      class="select-trigger"
      type="button"
      role="combobox"
      :aria-labelledby="`${id}-label`"
      aria-haspopup="listbox"
      :aria-expanded="opened"
      :aria-controls="opened ? `${id}-list` : undefined"
      :aria-invalid="invalid || undefined"
      :aria-describedby="invalid ? `${id}-error` : undefined"
      :aria-required="required || undefined"
      :disabled="disabled"
      @click="opened ? close() : show()"
      @keydown.down.prevent="show"
      @keydown.up.prevent="show"
      @keydown.esc.prevent="close()"
    >
      <span class="select-summary" :title="summary">{{ summary }}</span
      ><span aria-hidden="true" class="select-chevron">⌄</span>
    </button>
    <!-- Retain native form validation without exposing a second control to assistive technology. -->
    <select
      v-if="required"
      class="select-validation"
      tabindex="-1"
      aria-hidden="true"
      :required="required"
      :disabled="disabled"
      :multiple="multiple"
      :value="model ?? (multiple ? [] : '')"
      @invalid.prevent="
        invalid = true;
        show();
      "
    >
      <option v-if="!multiple" value="" />
      <option v-for="choice in choices" :key="choice.id" :value="choice.id">
        {{ choice.name }}
      </option>
    </select>
    <div v-if="opened" class="select-popup">
      <input
        ref="searchInput"
        v-model="query"
        type="search"
        class="select-search"
        :aria-label="`${label} durchsuchen`"
        placeholder="Suchen …"
        autocomplete="off"
        :aria-controls="`${id}-list`"
        :aria-activedescendant="activeId"
        @keydown="keydown"
      />
      <ul
        :id="`${id}-list`"
        role="listbox"
        :aria-label="label"
        :aria-multiselectable="multiple || undefined"
        class="select-options"
      >
        <li
          v-for="(choice, index) in options"
          :id="`${id}-option-${index}`"
          :key="choice.id ?? 'empty'"
          role="option"
          :aria-selected="selected(choice.id)"
          :class="{
            'is-active': index === active,
            'is-selected': selected(choice.id),
          }"
          @mousedown.prevent
          @click="pick(choice.id)"
          @mousemove="active = index"
        >
          <span>{{ choice.name }}</span
          ><span v-if="selected(choice.id)" aria-hidden="true">✓</span>
        </li>
      </ul>
      <p v-if="!options.length" class="select-empty" role="status">
        Keine passenden Einträge.
      </p>
    </div>
    <p v-if="invalid" :id="`${id}-error`" class="select-error" role="alert">
      Bitte eine Auswahl treffen.
    </p>
  </div>
</template>
