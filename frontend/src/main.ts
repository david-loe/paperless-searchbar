import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import Login from "./views/Login.vue";
import Search from "./views/Search.vue";
import { refreshSession, session } from "./api";
import "./style.css";
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: Login },
    { path: "/", component: Search },
    { path: "/documents/:id", component: () => import("./views/Document.vue") },
    { path: "/admin", component: () => import("./views/Admin.vue") },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});
router.beforeEach(async (to) => {
  if (!session.value) {
    try {
      await refreshSession();
    } catch {
      return to.path === "/login" ? true : "/login";
    }
  }
  if (to.path !== "/login" && !session.value?.authenticated) return "/login";
  if (to.path === "/admin" && !session.value?.is_admin) return "/";
});
window.addEventListener("session-expired", () => {
  void router.replace("/login");
});
// Recheck access on focus and regularly, including while a PDF is open.
window.addEventListener("focus", () => {
  void refreshSession().catch(() => {});
});
setInterval(() => {
  if (session.value?.authenticated)
    void refreshSession().catch(() => {
      session.value = null;
    });
}, 30000);
createApp(App).use(router).mount("#app");
