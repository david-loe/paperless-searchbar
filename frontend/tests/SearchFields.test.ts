import { mount } from "@vue/test-utils";
import { describe, it, expect } from "vitest";
import SearchFields from "../src/components/SearchFields.vue";
import type { CustomField, CustomFilter } from "../src/types";
const fields: CustomField[] = [
  {
    id: 1,
    name: "Mandant",
    data_type: "string",
    operators: ["exact"],
    options: [],
  },
  {
    id: 2,
    name: "Bezahlt",
    data_type: "boolean",
    operators: ["exact"],
    options: [],
  },
  {
    id: 3,
    name: "Anzahl",
    data_type: "integer",
    operators: ["exact"],
    options: [],
  },
  {
    id: 4,
    name: "Verweise",
    data_type: "documentlink",
    operators: ["exact"],
    options: [],
  },
  {
    id: 5,
    name: "Kategorie",
    data_type: "select",
    operators: ["exact"],
    options: [{ id: "a", label: "Vertrag" }],
  },
];
function form() {
  const wrapper = mount(SearchFields, {
    props: {
      fields,
      modelValue: [] as CustomFilter[],
      "onUpdate:modelValue": (value: CustomFilter[]) => {
        void wrapper.setProps({ modelValue: value });
      },
    },
  });
  return wrapper;
}
describe("Direkte Suchfelder", () => {
  it("preserves false, zero and select IDs as exact filters; clearing omits a field", async () => {
    const wrapper = form();
    await wrapper.findAll("select")[0]!.setValue("false");
    await wrapper.find('input[type="number"]').setValue("0");
    await wrapper.findAll("select")[1]!.setValue("a");
    expect(wrapper.props("modelValue")).toEqual([
      { field: 2, op: "exact", value: false },
      { field: 3, op: "exact", value: 0 },
      { field: 5, op: "exact", value: "a" },
    ]);
    await wrapper.findAll("select")[0]!.setValue("");
    expect(wrapper.props("modelValue").some((f) => f.field === 2)).toBe(false);
  });
  it("preserves exact text and lets users type a list of document IDs, then reset", async () => {
    const wrapper = form();
    await wrapper.find('input[placeholder="Mandant"]').setValue(" A ");
    const links = wrapper.find('input[placeholder^="Dokument-IDs"]');
    await links.setValue("101,");
    expect((links.element as HTMLInputElement).value).toBe("101,");
    await links.setValue("101, 202");
    expect(wrapper.props("modelValue")).toEqual([
      { field: 1, op: "exact", value: " A " },
      { field: 4, op: "exact", value: [101, 202] },
    ]);
    await wrapper.setProps({ modelValue: [] });
    expect((links.element as HTMLInputElement).value).toBe("");
  });
});
