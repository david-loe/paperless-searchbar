import { mount } from "@vue/test-utils";
import { describe, it, expect } from "vitest";
import CustomFilters from "../src/components/CustomFilters.vue";
import ChoiceSelect from "../src/components/ChoiceSelect.vue";
import type { CustomField } from "../src/types";
const fields: CustomField[] = [
  {
    id: 1,
    name: "Termin",
    data_type: "date",
    operators: ["exact", "range"],
    options: [],
  },
  {
    id: 2,
    name: "Bezahlt",
    data_type: "boolean",
    operators: ["exact", "exists"],
    options: [],
  },
  {
    id: 3,
    name: "Kategorie",
    data_type: "select",
    operators: ["exact", "in"],
    options: [{ id: "a", label: "Vertrag" }],
  },
];
describe("Custom-Field-Eingaben", () => {
  it("offers a date input and two values for a date range", async () => {
    const value = [{ field: 1, op: "exact", value: "2026-01-01" }];
    const wrapper = mount(CustomFilters, {
      props: { fields, modelValue: value },
    });
    expect(wrapper.find("input").attributes("type")).toBe("date");
    await wrapper.findAll("select")[1]!.setValue("range");
    expect(wrapper.findAll('input[type="date"]')).toHaveLength(2);
    await wrapper.findAll("input")[0]!.setValue("2026-02-01");
    await wrapper.findAll("input")[1]!.setValue("2026-03-01");
    expect(value[0]!.value).toEqual(["2026-02-01", "2026-03-01"]);
  });
  it("preserves boolean false and uses select option IDs", async () => {
    const value = [{ field: 2, op: "exact", value: true }];
    const wrapper = mount(CustomFilters, {
      props: { fields, modelValue: value },
    });
    await wrapper.findAll("select")[2]!.setValue("false");
    expect(value[0]!.value).toBe(false);
    const select = mount(CustomFilters, {
      props: { fields, modelValue: [{ field: 3, op: "in", value: [] }] },
    });
    await select.find("select[multiple]").setValue(["a"]);
    expect(select.props("modelValue")[0]!.value).toEqual(["a"]);
  });
});
describe("Auswahlfilter", () => {
  it("shows choices directly and emits the selected ID", async () => {
    const wrapper = mount(ChoiceSelect, {
      props: {
        label: "Speicherpfad",
        modelValue: 1,
        choices: [
          { id: 1, name: "Privat" },
          { id: 2, name: "Buchhaltung" },
        ],
      },
    });
    expect(wrapper.find("input").exists()).toBe(false);
    expect(wrapper.findAll("option").map((v) => v.text())).toContain("Privat");
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    await wrapper.find("select").setValue("2");
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([2]);
  });
});
