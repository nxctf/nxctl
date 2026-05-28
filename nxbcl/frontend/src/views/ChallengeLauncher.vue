<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { issuePow, listChallenges, startChallenge, submitPow, getInstance, extendChallenge, checkChallenge } from "../api.js";
import { solvePow } from "../pow.js";
import type { Challenge, ChallengeState, InstanceInfo } from "../types.js";
import CopyField from "../components/CopyField.vue";

const props = defineProps<{ id: string }>();
const router = useRouter();

const challenge = ref<Challenge | null>(null);
const instance = ref<InstanceInfo | null>(null);
const state = ref<ChallengeState>("idle");
const errorMsg = ref("");
const powProgress = ref("");
const loading = ref(true);

const flag = ref("");
const checking = ref(false);
const extending = ref(false);
const extendMsg = ref("");

const secondsLeft = ref<number>(999999);
const timeLeftStr = ref<string>("");
let timerIntervalId: any = null;

const updateCountdown = () => {
  if (!instance.value || !instance.value.expires_at) {
    secondsLeft.value = 999999;
    timeLeftStr.value = "";
    return;
  }
  const expiry = new Date(instance.value.expires_at).getTime();
  const now = new Date().getTime();
  const diff = Math.max(0, Math.floor((expiry - now) / 1000));
  secondsLeft.value = diff;

  if (diff === 0) {
    timeLeftStr.value = "Expired";
    instance.value.status = "expired";
    state.value = "idle";
    stopTimer();
    return;
  }

  const m = Math.floor(diff / 60);
  const s = diff % 60;
  timeLeftStr.value = `${m}:${s < 10 ? '0' : ''}${s}`;
};

const startTimer = () => {
  if (timerIntervalId) clearInterval(timerIntervalId);
  updateCountdown();
  timerIntervalId = setInterval(updateCountdown, 1000);
};

const stopTimer = () => {
  if (timerIntervalId) {
    clearInterval(timerIntervalId);
    timerIntervalId = null;
  }
};

const rpcUrl = computed(() => {
  if (!instance.value) return "";
  return instance.value.rpc_url || `http://localhost:${instance.value.rpc_port || 8545}`;
});

const setupAddr = computed(() => {
  if (!instance.value) return "";
  return instance.value.setup_address || instance.value.deploy_address || "";
});

const envBlock = computed(() => {
  if (!instance.value) return "";
  return [
    `export RPC_URL="${rpcUrl.value}"`,
    `export PRIVKEY="${instance.value.private_key}"`,
    `export SETUP_ADDR="${setupAddr.value}"`,
  ].join("\n");
});

onMounted(async () => {
  try {
    const list = await listChallenges();
    challenge.value = list.find((c) => c.id === props.id) || null;
    if (!challenge.value) {
      errorMsg.value = `Challenge "${props.id}" not found`;
      return;
    }

    // Try to load any existing active instance
    try {
      const activeInst = await getInstance(props.id);
      if (activeInst && activeInst.status === "running") {
        instance.value = activeInst;
        state.value = "active";
        startTimer();
      }
    } catch {
      // If no active instance found or unauthorized, keep state as idle
    }
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : "Failed to load challenge";
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => {
  stopTimer();
});

async function launch(restart = false) {
  if (!challenge.value) return;
  errorMsg.value = "";
  flag.value = "";
  extendMsg.value = "";

  try {
    // Step 1: PoW
    state.value = "pow";
    powProgress.value = "Requesting PoW challenge...";
    const pow = await issuePow(props.id);

    powProgress.value = `Solving PoW (prefix: ${pow.zero_prefix})...`;
    const solution = await solvePow(pow.salt, pow.zero_prefix);

    // Step 2: Submit PoW → get session
    state.value = "session";
    powProgress.value = "Verifying solution...";
    await submitPow(props.id, pow.challenge_token, solution);

    // Step 3: Start / Restart instance
    state.value = "launching";
    powProgress.value = restart ? "Restarting instance..." : "Launching instance...";
    const inst = await startChallenge(props.id, restart);
    instance.value = inst;
    state.value = "active";
    powProgress.value = "";
    startTimer();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : "Launch failed";
    state.value = "error";
    powProgress.value = "";
  }
}

async function handleCheck() {
  if (!instance.value || checking.value) return;
  checking.value = true;
  errorMsg.value = "";
  try {
    const res = await checkChallenge(props.id);
    if (res.solved && res.flag) {
      flag.value = res.flag;
    } else {
      errorMsg.value = res.message || "Not solved yet.";
      state.value = "error";
    }
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : "Verification failed";
    state.value = "error";
  } finally {
    checking.value = false;
  }
}

async function handleExtend() {
  if (!instance.value || extending.value) return;
  extending.value = true;
  extendMsg.value = "";
  errorMsg.value = "";
  try {
    const res = await extendChallenge(props.id);
    if (res.status === "success") {
      if (instance.value) {
        instance.value.expires_at = res.expires_at;
        startTimer();
      }
      extendMsg.value = `Instance extended successfully!`;
    }
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : "Extension failed";
    state.value = "error";
  } finally {
    extending.value = false;
  }
}

async function copyFullEnv() {
  if (!envBlock.value) return;
  try {
    await navigator.clipboard.writeText(envBlock.value);
  } catch {
    /* noop */
  }
}

const isLaunching = computed(() =>
  ["pow", "session", "launching"].includes(state.value),
);

const stateLabel = computed(() => {
  switch (state.value) {
    case "pow":
      return "Solving PoW";
    case "session":
      return "Verifying";
    case "launching":
      return "Launching";
    case "active":
      return "Active";
    case "error":
      return "Error";
    default:
      return "Ready";
  }
});

const stateColor = computed(() => {
  switch (state.value) {
    case "active":
      return "text-ok";
    case "error":
      return "text-danger";
    case "pow":
    case "session":
    case "launching":
      return "text-warn";
    default:
      return "text-text-muted";
  }
});
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 py-8 animate-fade-in">
    <!-- Back link -->
    <button
      @click="router.push({ name: 'challenges' })"
      class="inline-flex items-center gap-1.5 text-text-muted hover:text-accent text-sm font-medium transition-colors mb-6 cursor-pointer bg-transparent border-none p-0"
    >
      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M19 12H5M12 19l-7-7 7-7" />
      </svg>
      Back to Challenges
    </button>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-24">
      <div class="flex items-center gap-3 text-text-muted">
        <svg class="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span class="text-sm">Loading...</span>
      </div>
    </div>

    <!-- Not found -->
    <div
      v-else-if="!challenge"
      class="glass rounded-xl p-8 text-center"
    >
      <p class="text-danger font-semibold">Challenge not found</p>
      <p class="text-text-muted text-sm mt-2">{{ errorMsg }}</p>
    </div>

    <!-- Challenge Detail -->
    <template v-else>
      <!-- Challenge Header -->
      <div class="glass rounded-xl p-6 mb-4 animate-slide-up">
        <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-3 mb-2">
              <h2 class="text-xl sm:text-2xl font-bold text-text truncate">
                {{ challenge.name || challenge.id }}
              </h2>
              <span
                v-if="challenge.category"
                class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-accent-dim text-accent border border-accent/20 flex-shrink-0"
              >
                {{ challenge.category }}
              </span>
            </div>
            <p class="text-xs text-text-muted font-mono mb-3">{{ challenge.id }}</p>
            <p class="text-sm text-text-muted leading-relaxed">
              {{ challenge.description || "Blockchain challenge" }}
            </p>
          </div>

          <!-- Status -->
          <div class="flex-shrink-0 flex items-center gap-2">
            <span
              class="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full border"
              :class="[
                stateColor,
                state === 'active'
                  ? 'border-ok/30 bg-ok-dim/30'
                  : state === 'error'
                    ? 'border-danger/30 bg-danger-dim/30'
                    : isLaunching
                      ? 'border-warn/30 bg-warn-dim/30'
                      : 'border-border bg-surface-2',
              ]"
            >
              <span
                v-if="isLaunching"
                class="w-1.5 h-1.5 rounded-full bg-current animate-pulse-soft"
              ></span>
              <span
                v-else-if="state === 'active'"
                class="w-1.5 h-1.5 rounded-full bg-ok"
              ></span>
              {{ stateLabel }}
            </span>
          </div>
        </div>

        <!-- Meta chips -->
        <div class="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t border-border/50">
          <span
            v-if="challenge.chain_family"
            class="text-[11px] font-medium text-text-muted bg-surface-2 px-2 py-1 rounded-md"
          >
            {{ challenge.chain_family?.toUpperCase() }}
          </span>
          <span
            v-if="challenge.chain_id"
            class="text-[11px] font-medium text-text-muted bg-surface-2 px-2 py-1 rounded-md"
          >
            Chain {{ challenge.chain_id }}
          </span>
          <span
            v-if="challenge.protocol"
            class="text-[11px] font-medium text-text-muted bg-surface-2 px-2 py-1 rounded-md"
          >
            {{ challenge.protocol?.toUpperCase() }}
          </span>
        </div>
      </div>

      <!-- Action Panel -->
      <div
        class="glass rounded-xl p-6 mb-4 animate-slide-up"
        style="animation-delay: 80ms; animation-fill-mode: backwards"
      >
        <h3 class="text-sm font-bold text-text uppercase tracking-wider mb-4">Actions</h3>

        <!-- Launch progress -->
        <div
          v-if="powProgress"
          class="mb-4 flex items-center gap-3 p-3 rounded-lg bg-surface-2 border border-border"
        >
          <svg class="animate-spin h-4 w-4 text-warn flex-shrink-0" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span class="text-sm text-text-muted">{{ powProgress }}</span>
        </div>

        <!-- Error message -->
        <div
          v-if="errorMsg && (state === 'error' || state === 'active')"
          class="mb-4 p-3 rounded-lg bg-danger-dim/30 border border-danger/20"
        >
          <p class="text-sm text-danger">{{ errorMsg }}</p>
        </div>

        <!-- Flag message -->
        <div
          v-if="flag"
          class="mb-4 p-4 rounded-lg bg-emerald-500/20 border border-emerald-500/40 animate-pulse-soft"
        >
          <h4 class="text-sm font-bold text-ok uppercase tracking-wider mb-2">🎉 Solved! Flag Discovered:</h4>
          <pre class="text-xs leading-relaxed p-3 rounded bg-surface border border-emerald-500/30 font-mono text-emerald-300 select-all cursor-pointer">{{ flag }}</pre>
        </div>

        <!-- Extend message -->
        <div
          v-if="extendMsg"
          class="mb-4 p-3 rounded-lg bg-accent-dim/30 border border-accent/20"
        >
          <p class="text-sm text-accent">{{ extendMsg }}</p>
        </div>

        <!-- Action Buttons Layout -->
        <div class="space-y-5">
          <!-- Primary Actions -->
          <div class="flex flex-col sm:flex-row gap-3">
            <button
              v-if="instance"
              @click="handleCheck"
              :disabled="checking || isLaunching"
              class="flex-1 px-6 py-3 rounded-xl text-sm font-bold bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-bg hover:shadow-lg hover:shadow-emerald-500/10 active:translate-y-px transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 border-none"
            >
              <svg v-if="checking" class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span v-else class="text-sm">✔️</span>
              {{ checking ? "Checking Solution..." : "Check Solution" }}
            </button>

            <button
              v-if="instance"
              @click="copyFullEnv"
              class="flex-1 px-6 py-3 rounded-xl text-sm font-bold border border-border bg-surface-2 text-text hover:bg-surface-3 hover:border-border-hover hover:shadow-md transition-all duration-200 cursor-pointer flex items-center justify-center gap-2"
            >
              <span>📋</span>
              Copy All Env
            </button>
          </div>

          <!-- Divider for Session Management -->
          <div v-if="instance" class="border-t border-border/40 my-1"></div>

          <!-- Session Controls -->
          <div class="flex flex-wrap items-center gap-3">
            <span v-if="instance" class="text-xs font-bold text-text-muted mr-1 hidden md:inline">Session:</span>

            <!-- Start / Re-Launch -->
            <button
              @click="launch(false)"
              :disabled="isLaunching"
              class="px-4 py-2.5 rounded-lg text-xs font-bold transition-all duration-200 cursor-pointer border flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
              :class="
                state === 'active'
                  ? 'border-border bg-surface-2 text-text hover:bg-surface-3 hover:border-border-hover'
                  : 'border-transparent bg-gradient-to-r from-accent to-emerald-500 text-bg hover:shadow-md hover:-translate-y-px active:translate-y-0'
              "
            >
              <span>⟳</span>
              {{ state === 'active' ? 'Re-Launch New Session' : 'Start Instance' }}
            </button>

            <!-- Extend time (Only active when under threshold) -->
            <button
              v-if="instance"
              @click="handleExtend"
              :disabled="extending || isLaunching || secondsLeft > (instance.extend_threshold_seconds || 300)"
              class="px-4 py-2.5 rounded-lg text-xs font-bold border transition-all duration-200 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
              :class="
                secondsLeft > (instance.extend_threshold_seconds || 300)
                  ? 'border-border bg-surface-2 text-text-muted cursor-not-allowed'
                  : 'border-accent/20 bg-accent/10 text-accent hover:bg-accent/20 hover:border-accent/40'
              "
              :title="secondsLeft > (instance.extend_threshold_seconds || 300) ? `You can only extend when under ${Math.round((instance.extend_threshold_seconds || 300) / 60)} minutes left!` : 'Extend session'"
            >
              <svg v-if="extending" class="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span v-else>➕</span>
              {{ secondsLeft > (instance.extend_threshold_seconds || 300) ? 'Extend (Locked)' : (extending ? 'Extending...' : `Extend +${Math.round((instance.extend_seconds || 300) / 60)}m`) }}
            </button>

            <!-- Restart / Reset -->
            <button
              @click="launch(true)"
              :disabled="isLaunching"
              class="px-4 py-2.5 rounded-lg text-xs font-bold border border-danger/20 bg-danger/10 text-danger hover:bg-danger/20 hover:border-danger/40 transition-all duration-200 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              <span>↻</span>
              Reset State (Restart)
            </button>
          </div>

          <!-- Microtext guidelines -->
          <div v-if="instance" class="text-[11px] text-text-muted flex items-start gap-1.5 bg-surface/50 p-2.5 rounded-lg border border-border/30">
            <span class="text-xs">💡</span>
            <p class="leading-normal">
              <strong>Extend +{{ Math.round((instance.extend_seconds || 300) / 60) }}m</strong> keeps your active session alive (unlocked only when remaining time is less than {{ Math.round((instance.extend_threshold_seconds || 300) / 60) }} minutes).
              <strong>Reset State</strong> completely redeploys fresh contracts for a clean start.
            </p>
          </div>
        </div>
      </div>

      <!-- Instance Data -->
      <div
        v-if="instance"
        class="glass rounded-xl p-6 animate-slide-up"
        style="animation-delay: 160ms; animation-fill-mode: backwards"
      >
        <div class="flex items-center justify-between mb-5">
          <h3 class="text-sm font-bold text-text uppercase tracking-wider">Instance Data</h3>
          <span
            v-if="instance.expires_at"
            class="text-[11px] font-mono px-2.5 py-1 rounded-md flex items-center gap-1.5 transition-all duration-300"
            :class="secondsLeft < (instance.extend_threshold_seconds || 300) ? 'bg-danger-dim/30 text-danger border border-danger/20 animate-pulse-soft' : 'bg-surface-2 text-text-muted border border-border/40'"
          >
            ⏳ {{ timeLeftStr ? `Expires in: ${timeLeftStr}` : 'Expired' }}
          </span>
        </div>

        <div class="space-y-1">
          <CopyField label="RPC URL" :value="rpcUrl" />
          <CopyField label="Private Key" :value="instance.private_key" />
          <CopyField label="Setup Contract" :value="setupAddr" />
          <CopyField
            v-if="instance.wallet_address"
            label="Wallet Address"
            :value="instance.wallet_address"
          />
          <CopyField
            v-if="instance.chain_id"
            label="Chain ID"
            :value="String(instance.chain_id)"
          />
        </div>

        <!-- Full env block -->
        <div class="mt-5 pt-5 border-t border-border/50">
          <div class="flex items-center justify-between mb-2">
            <span class="text-[11px] text-text-muted font-bold uppercase tracking-wide"
              >Solver Script</span
            >
            <button
              @click="copyFullEnv"
              class="text-[11px] text-accent hover:text-accent-hover font-semibold transition-colors cursor-pointer bg-transparent border-none p-0"
            >
              Copy
            </button>
          </div>
          <pre
            class="text-xs leading-relaxed p-4 rounded-lg bg-terminal-bg text-terminal-text border border-border font-mono overflow-x-auto"
          >{{ envBlock }}</pre>
        </div>
      </div>
    </template>
  </div>
</template>
