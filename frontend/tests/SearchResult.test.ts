import { mount } from "@vue/test-utils";
import { describe, it, expect } from "vitest";
import SearchResult from "../src/components/SearchResult.vue";
import type { CustomField, Document } from "../src/types";
const document: Document = {
  id: 101,
  title: "Rechnung Firma A",
  created: "2026-10-01T00:00:00Z",
  correspondent: "Firma A",
  storage_path: null,
  document_type: "Rechnung",
  paperless_url: "https://example.test/documents/101/",
  custom_fields: [
    { field: 1, name: "Bezahlt", value: false },
    { field: 2, name: "Anzahl", value: 0 },
    { field: 4, name: "Intern", value: "Nicht in Trefferliste" },
  ],
};
const fields: CustomField[] = [
  {
    id: 1,
    name: "Bezahlt",
    data_type: "boolean",
    operators: ["exact"],
    options: [],
  },
  {
    id: 2,
    name: "Anzahl",
    data_type: "integer",
    operators: ["exact"],
    options: [],
  },
  {
    id: 3,
    name: "Termin",
    data_type: "date",
    operators: ["exact"],
    options: [],
  },
];
describe("Treffervorschau", () => {
  it("labels metadata and only configured fields, preserving false, zero and missing values", async () => {
    const wrapper = mount(SearchResult, {
      props: { document, fields },
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    });
    expect(wrapper.find("h3").text()).toBe("Rechnung Firma A");
    expect(wrapper.findAll("dt").map((item) => item.text())).toEqual([
      "Dokument-ID",
      "Datum",
      "Dokumenttyp",
      "Korrespondent",
      "Speicherpfad",
      "Bezahlt",
      "Anzahl",
      "Termin",
    ]);
    expect(wrapper.findAll("dd").map((item) => item.text())).toEqual([
      "#101",
      "01.10.2026",
      "Rechnung",
      "Firma A",
      "—",
      "Nein",
      "0",
      "—",
    ]);
    expect(wrapper.text()).not.toContain("Nicht in Trefferliste");
    expect(wrapper.find("img").attributes("src")).toBe(
      "/api/documents/101/thumb",
    );
    expect(wrapper.find("img").attributes("loading")).toBe("lazy");
    await wrapper.find("img").trigger("error");
    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.find('[role="img"]').attributes("aria-label")).toBe(
      "Keine Miniaturansicht verfügbar",
    );
    expect(wrapper.find("h3").text()).toBe("Rechnung Firma A");
  });
});
