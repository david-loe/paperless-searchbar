<script setup lang="ts">
import { useRouter } from "vue-router";
import { api, session, refreshSession } from "./api";
import { watch } from "vue";
const router = useRouter();
watch(
  () => session.value?.authenticated,
  (value) => {
    if (!value && router.currentRoute.value.path !== "/login")
      void router.replace("/login");
  },
);
async function logout() {
  try {
    await api("/auth/logout", {});
  } finally {
    session.value = null;
    await refreshSession();
    await router.replace("/login");
  }
}
</script>
<template>
  <header class="topbar">
    <RouterLink to="/" class="brand"
      ><span class="brand-icon">▤</span
      ><span
        >paperless<span class="brand-light"> / searchbar</span></span
      ></RouterLink
    >
    <nav v-if="session?.authenticated" aria-label="Hauptnavigation">
      <RouterLink to="/">Suche</RouterLink
      ><RouterLink v-if="session.is_admin" to="/admin">Verwaltung</RouterLink
      ><span class="user-name">{{ session.name }}</span
      ><button class="ghost" @click="logout">Abmelden</button>
    </nav>
  </header>
  <main><RouterView :key="$route.path" /></main>
</template>
