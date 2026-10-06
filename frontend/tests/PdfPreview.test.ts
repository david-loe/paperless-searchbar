import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import PdfPreview from "../src/components/PdfPreview.vue";

const pdf = vi.hoisted(() => ({
  render: vi.fn(),
  getPage: vi.fn(),
  destroy: vi.fn(),
  cancel: vi.fn(),
}));
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({
    promise: Promise.resolve({ numPages: 3, getPage: pdf.getPage }),
    destroy: pdf.destroy,
  }),
}));
let resize: () => void;
let width: number;
const disconnect = vi.fn();
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  width = 800;
  pdf.render.mockImplementation(() => ({
    promise: Promise.resolve(),
    cancel: pdf.cancel,
  }));
  pdf.getPage.mockResolvedValue({
    getViewport: ({ scale }: { scale: number }) => ({
      width: 600 * scale,
      height: 800 * scale,
    }),
    render: pdf.render,
  });
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(
    () => width,
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    {} as CanvasRenderingContext2D,
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: () => void) {
        resize = callback;
      }
      observe() {}
      disconnect = disconnect;
    },
  );
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("ignores unchanged widths, debounces real resizes and retains page/zoom controls", async () => {
  const wrapper = mount(PdfPreview, { props: { url: "/test.pdf" } });
  await flushPromises();
  expect(pdf.render).toHaveBeenCalledTimes(1);
  resize(); // Initial observation and height-only changes need no extra render.
  resize();
  await vi.advanceTimersByTimeAsync(200);
  expect(pdf.render).toHaveBeenCalledTimes(1);
  width = 700;
  resize();
  width = 650;
  resize();
  await vi.advanceTimersByTimeAsync(150);
  expect(pdf.render).toHaveBeenCalledTimes(2);
  await wrapper.find("select").setValue("1.5");
  await flushPromises();
  expect(pdf.render).toHaveBeenCalledTimes(3);
  await wrapper.find('[aria-label="Nächste PDF-Seite"]').trigger("click");
  await flushPromises();
  expect(pdf.getPage).toHaveBeenLastCalledWith(2);
  expect(wrapper.text()).toContain("Seite 2 von 3");
  width = 900;
  resize();
  wrapper.unmount();
  await vi.advanceTimersByTimeAsync(200);
  expect(pdf.render).toHaveBeenCalledTimes(4);
  expect(disconnect).toHaveBeenCalledOnce();
  expect(pdf.destroy).toHaveBeenCalledOnce();
});
