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
    <div class="login-card">
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
    </div>
  </section>
</template>
