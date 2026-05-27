<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { issuePow, listChallenges, startChallenge, submitPow } from "./api.js";
import { solvePow } from "./pow.js";
import type { Challenge, InstanceInfo } from "./types.js";

type ChallengeState = "idle" | "pow" | "session" | "launching" | "running" | "error";

const challenges = ref<Challenge[]>([]);
const userId = ref(localStorage.getItem("nxbcl_user_id") || "local-user");
const loading = ref(false);
const error = ref("");
const stateByChallenge = ref<Record<string, ChallengeState>>({});
const instanceByChallenge = ref<Record<string, InstanceInfo>>({});
const errorByChallenge = ref<Record<string, string>>({});

const apiStatus = computed(() => (error.value ? "offline" : "online"));

function setUserId() {
  localStorage.setItem("nxbcl_user_id", userId.value.trim() || "local-user");
}

function setState(challengeId: string, state: ChallengeState) {
  stateByChallenge.value = { ...stateByChallenge.value, [challengeId]: state };
}

function currentState(challengeId: string): ChallengeState {
  return stateByChallenge.value[challengeId] || "idle";
}

function instanceEnv(challengeId: string, instance: InstanceInfo): string {
  const rpcUrl = instance.rpc_url || `http://localhost:${instance.rpc_port || 8545}`;
  const setupAddr = instance.setup_address || instance.deploy_address || "";
  return [
    `export RPC_URL=${rpcUrl}`,
    `export PRIVKEY=${instance.private_key}`,
    `export SETUP_ADDR=${setupAddr}`,
    `cd challenges/${challengeId}`,
    "python3 solve.py",
  ].join("\n");
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    challenges.value = await listChallenges();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load challenges";
  } finally {
    loading.value = false;
  }
}

async function launch(challenge: Challenge, restart = false) {
  const id = challenge.id;
  const user = userId.value.trim();
  if (!user) {
    errorByChallenge.value = { ...errorByChallenge.value, [id]: "User ID is required" };
    return;
  }

  setUserId();
  errorByChallenge.value = { ...errorByChallenge.value, [id]: "" };

  try {
    setState(id, "pow");
    const pow = await issuePow(id, user);
    const solution = await solvePow(pow.salt, pow.zero_prefix);

    setState(id, "session");
    await submitPow(id, user, pow.challenge_token, solution);

    setState(id, "launching");
    const instance = await startChallenge(id, user, restart);
    instanceByChallenge.value = { ...instanceByChallenge.value, [id]: instance };
    setState(id, "running");
  } catch (err) {
    errorByChallenge.value = {
      ...errorByChallenge.value,
      [id]: err instanceof Error ? err.message : "Launch failed",
    };
    setState(id, "error");
  }
}

async function copyEnv(challengeId: string) {
  const instance = instanceByChallenge.value[challengeId];
  if (!instance) {
    return;
  }
  await navigator.clipboard.writeText(instanceEnv(challengeId, instance));
}

onMounted(load);
</script>

<template>
  <header>
    <div class="shell topbar">
      <h1>NXBCL Launcher</h1>
      <span class="badge" :class="{ ok: apiStatus === 'online' }">{{ apiStatus }}</span>
    </div>
  </header>

  <main class="shell">
    <section class="toolbar">
      <div>
        <label for="user-id">User ID</label>
        <input id="user-id" v-model="userId" autocomplete="off" @change="setUserId">
      </div>
      <button @click="load">Reload</button>
    </section>

    <div v-if="loading" class="notice">Loading challenges...</div>
    <div v-else-if="error" class="notice error">{{ error }}</div>
    <div v-else-if="!challenges.length" class="notice">No challenges found.</div>

    <section v-else class="grid">
      <article v-for="challenge in challenges" :key="challenge.id" class="card">
        <div class="card-head">
          <div>
            <h2>{{ challenge.name || challenge.id }}</h2>
            <p class="id">{{ challenge.id }}</p>
          </div>
          <span class="badge" :class="{ ok: currentState(challenge.id) === 'running', warn: ['pow', 'session', 'launching'].includes(currentState(challenge.id)) }">
            {{ currentState(challenge.id) === 'idle' ? (challenge.kind || 'challenge') : currentState(challenge.id) }}
          </span>
        </div>

        <p class="desc">{{ challenge.description || 'Blockchain challenge' }}</p>

        <div class="actions">
          <button class="primary" :disabled="['pow', 'session', 'launching'].includes(currentState(challenge.id))" @click="launch(challenge)">
            Start
          </button>
          <button :disabled="['pow', 'session', 'launching'].includes(currentState(challenge.id))" @click="launch(challenge, true)">
            Restart
          </button>
          <button :disabled="!instanceByChallenge[challenge.id]" @click="copyEnv(challenge.id)">
            Copy Env
          </button>
        </div>

        <div v-if="errorByChallenge[challenge.id]" class="output error">
          {{ errorByChallenge[challenge.id] }}
        </div>

        <pre v-if="instanceByChallenge[challenge.id]" class="output active">{{ instanceEnv(challenge.id, instanceByChallenge[challenge.id]) }}</pre>
      </article>
    </section>
  </main>
</template>
