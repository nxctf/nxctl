import { createRouter, createWebHashHistory } from "vue-router";
import ChallengeList from "./views/ChallengeList.vue";
import ChallengeLauncher from "./views/ChallengeLauncher.vue";

const routes = [
  { path: "/", redirect: "/challenges" },
  { path: "/challenges", name: "challenges", component: ChallengeList },
  {
    path: "/challenges/:id",
    name: "challenge-detail",
    component: ChallengeLauncher,
    props: true,
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

export default router;
