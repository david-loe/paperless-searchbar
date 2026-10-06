<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, errorMessage, refreshSession, session } from "../api";
const router = useRouter(),
  route = useRoute();
const code = ref(""),
  busy = ref(false);
const error = ref(
  route.query.error
    ? "OIDC-Anmeldung fehlgeschlagen. Bitte erneut versuchen."
    : "",
);
async function login() {
  busy.value = true;
  error.value = "";
  try {
    await api("/auth/code", { code: code.value });
    code.value = "";
    await refreshSession();
    await router.replace("/");
  } catch (e) {
    error.value = errorMessage(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <section class="login-layout">
    <div class="login-copy">
      <p class="eyebrow">DEIN DOKUMENTENZUGANG</p>
      <h1>Weniger suchen.<br />Mehr finden.</h1>
      <p>
        Ein direkter Weg zu den Dokumenten, die du brauchst. Übersichtlich,
        gezielt und an einem Ort.
      </p>
      <div class="paper-illustration" aria-hidden="true">
        <div class="paper">
          <span>▤</span><i></i><i></i><i></i><b>Gefunden.</b>
        </div>
      </div>
    </div>
    <div class="card login-card">
      <p class="eyebrow">PAPERLESS SEARCHBAR</p>
      <h2>Willkommen zurück</h2>
      <p class="muted">
        Gib deinen Zugangscode ein oder nutze dein Organisationskonto.
      </p>
      <p v-if="error" class="alert" role="alert">{{ error }}</p>
      <form @submit.prevent="login">
        <label
          >Zugangscode<input
            v-model="code"
            type="password"
            autocomplete="off"
            placeholder="Deinen Code eingeben"
            required /></label
        ><button class="primary wide" :disabled="busy">
          {{ busy ? "Anmeldung läuft …" : "Anmelden" }}
          <span aria-hidden="true">→</span>
        </button>
      </form>
      <template v-if="session?.oidc_enabled"
        ><div class="divider">oder</div>
        <a class="button secondary wide" href="/api/auth/oidc/login"
          >Mit Organisationskonto anmelden</a
        ></template
      >
      <p class="small muted">
        Dein Zugang bestimmt, welche Dokumente du sehen kannst.
      </p>
    </div>
  </section>
</template>
