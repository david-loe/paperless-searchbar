<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from "vue";
import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentLoadingTask,
  type PDFDocumentProxy,
  type RenderTask,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
GlobalWorkerOptions.workerSrc = workerUrl;
const props = defineProps<{ url: string }>();
const canvas = ref<HTMLCanvasElement | null>(null),
  container = ref<HTMLElement | null>(null);
const current = ref(1),
  pages = ref(0),
  zoom = ref(1),
  loading = ref(true),
  rendering = ref(false),
  error = ref("");
let task: PDFDocumentLoadingTask | undefined,
  pdf: PDFDocumentProxy | undefined,
  renderTask: RenderTask | undefined;
let observer: ResizeObserver | undefined,
  resizeTimer: ReturnType<typeof setTimeout> | undefined;
let active = true,
  generation = 0;
let observedWidth = 0;
async function render() {
  if (!pdf || !canvas.value || !container.value) return;
  const version = ++generation;
  rendering.value = true;
  const previous = renderTask;
  previous?.cancel();
  if (previous) await previous.promise.catch(() => {});
  try {
    const page = await pdf.getPage(current.value);
    if (!active || version !== generation || !canvas.value || !container.value)
      return;
    const fit =
      Math.max(200, container.value.clientWidth - 32) /
      page.getViewport({ scale: 1 }).width;
    const viewport = page.getViewport({ scale: fit * zoom.value });
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const element = canvas.value;
    element.width = Math.floor(viewport.width * ratio);
    element.height = Math.floor(viewport.height * ratio);
    element.style.width = `${viewport.width}px`;
    element.style.height = `${viewport.height}px`;
    const context = element.getContext("2d");
    if (!context) throw new Error("Canvas nicht verfügbar");
    renderTask = page.render({
      canvas: element,
      canvasContext: context,
      viewport,
      transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
    });
    await renderTask.promise;
  } catch (e) {
    if (
      active &&
      version === generation &&
      !(e instanceof Error && e.name === "RenderingCancelledException")
    )
      error.value =
        "Die PDF-Seite konnte nicht dargestellt werden. Du kannst die Datei herunterladen.";
  } finally {
    if (active && version === generation) rendering.value = false;
  }
}
onMounted(async () => {
  task = getDocument({
    url: props.url,
    withCredentials: true,
    cMapUrl: "/pdfjs/cmaps/",
    cMapPacked: true,
    standardFontDataUrl: "/pdfjs/standard_fonts/",
    wasmUrl: "/pdfjs/wasm/",
  });
  try {
    pdf = await task.promise;
    if (!active) return;
    pages.value = pdf.numPages;
    loading.value = false;
    await nextTick();
    await render();
    observedWidth = container.value?.clientWidth ?? 0;
    observer = new ResizeObserver(() => {
      const width = container.value?.clientWidth ?? 0;
      if (!active || width === observedWidth) return;
      observedWidth = width;
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => void render(), 150);
    });
    if (container.value) observer.observe(container.value);
  } catch {
    if (active) {
      loading.value = false;
      error.value =
        "Keine PDF-Vorschau verfügbar. Du kannst die Datei herunterladen.";
    }
  }
});
onUnmounted(() => {
  active = false;
  generation++;
  clearTimeout(resizeTimer);
  observer?.disconnect();
  renderTask?.cancel();
  void task?.destroy();
});
async function changePage(value: number) {
  current.value = value;
  await render();
}
async function changeZoom(value: number) {
  zoom.value = value;
  await render();
}
</script>
<template>
  <section class="pdf-viewer" aria-label="PDF-Vorschau">
    <div v-if="pages && !error" class="pdf-toolbar">
      <button
        class="ghost"
        aria-label="Vorherige PDF-Seite"
        :disabled="current === 1 || rendering"
        @click="changePage(current - 1)"
      >
        ←</button
      ><span>Seite {{ current }} von {{ pages }}</span
      ><button
        class="ghost"
        aria-label="Nächste PDF-Seite"
        :disabled="current === pages || rendering"
        @click="changePage(current + 1)"
      >
        →</button
      ><label class="pdf-zoom"
        >Zoom<select
          :value="zoom"
          @change="
            changeZoom(Number(($event.target as HTMLSelectElement).value))
          "
        >
          <option :value="1">Einpassen</option>
          <option :value="1.25">125 %</option>
          <option :value="1.5">150 %</option>
          <option :value="2">200 %</option>
        </select></label
      >
    </div>
    <p v-if="loading" role="status" class="empty">PDF wird geladen …</p>
    <p v-if="error" class="empty" role="status">{{ error }}</p>
    <div ref="container" class="pdf-canvas-container" :aria-busy="rendering">
      <canvas
        v-show="!loading && !error"
        ref="canvas"
        role="img"
        :aria-label="`PDF-Seite ${current}`"
        >Die PDF-Datei kann alternativ heruntergeladen werden.</canvas
      >
    </div>
  </section>
</template>
