import { enableAutoUnmount, mount, flushPromises } from "@vue/test-utils";
import { afterEach, describe, it, expect } from "vitest";
import SearchableSelect from "../src/components/SearchableSelect.vue";
enableAutoUnmount(afterEach);
const choices = [
  { id: 1, name: "Buchhaltung" },
  { id: 2, name: "Privat" },
];
describe("Suchbare Dropdowns", () => {
  it("filters only while open, keeps the selection, and supports keyboard selection", async () => {
    const wrapper = mount(SearchableSelect, {
      props: { label: "Speicherpfad", choices, modelValue: 2 },
      attachTo: document.body,
    });
    const trigger = wrapper.find('[role="combobox"]');
    expect(wrapper.find('input[type="search"]').exists()).toBe(false);
    await trigger.trigger("keydown", { key: "ArrowDown" });
    await flushPromises();
    const search = wrapper.find('input[type="search"]');
    expect(document.activeElement).toBe(search.element);
    await search.setValue("BUCH");
    expect(
      wrapper.findAll('[role="option"]').map((option) => option.text()),
    ).toEqual(["Buchhaltung"]);
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    await search.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([1]);
    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(trigger.element);
  });
  it("resets the query on opening; Escape and outside clicks preserve the selection", async () => {
    const wrapper = mount(SearchableSelect, {
      props: { label: "Speicherpfad", choices, modelValue: 1 },
      attachTo: document.body,
    });
    const trigger = wrapper.find('[role="combobox"]');
    await trigger.trigger("click");
    await wrapper.find("input").setValue("kein Treffer");
    expect(wrapper.find('[role="status"]').text()).toBe(
      "Keine passenden Einträge.",
    );
    await wrapper.find("input").trigger("keydown", { key: "Escape" });
    expect(trigger.attributes("aria-expanded")).toBe("false");
    await trigger.trigger("click");
    expect((wrapper.find("input").element as HTMLInputElement).value).toBe("");
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await flushPromises();
    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });
  it("keeps multi selections when filtering and emits string IDs unchanged", async () => {
    const wrapper = mount(SearchableSelect, {
      props: {
        label: "Kategorie",
        choices: [
          { id: "01", name: "Vertrag" },
          { id: "02", name: "Rechnung" },
        ],
        multiple: true,
        modelValue: ["01"],
      },
    });
    await wrapper.find('[role="combobox"]').trigger("click");
    await wrapper.find("input").setValue("rechnung");
    await wrapper.find('[role="option"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([["01", "02"]]);
    expect(wrapper.find('[role="combobox"]').attributes("aria-expanded")).toBe(
      "true",
    );
    await wrapper.setProps({ modelValue: ["01", "02"] });
    await wrapper.find('[role="option"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")?.[1]).toEqual([["01"]]);
  });
  it("supports clearing and preserves required and disabled form semantics", async () => {
    const wrapper = mount(SearchableSelect, {
      props: { label: "Profil", choices, modelValue: 1 },
      attachTo: document.body,
    });
    await wrapper.find('[role="combobox"]').trigger("click");
    await wrapper.find('[role="option"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([null]);
    await wrapper.setProps({ modelValue: null, required: true });
    const validation = wrapper.find("select").element as HTMLSelectElement;
    expect(validation.checkValidity()).toBe(false);
    await flushPromises();
    expect(wrapper.find('[role="alert"]').text()).toBe(
      "Bitte eine Auswahl treffen.",
    );
    await wrapper.setProps({ modelValue: 2 });
    expect(validation.checkValidity()).toBe(true);
    await wrapper.setProps({ disabled: true });
    expect(
      wrapper.find('[role="combobox"]').attributes("disabled"),
    ).toBeDefined();
    expect(wrapper.find("input").exists()).toBe(false);
  });
});
