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
const terminalLogs = ref<string[]>([
  `[${new Date().toLocaleTimeString()}] INFRASTRUCTURE: Establishing handshake with secure node...`,
  `[${new Date().toLocaleTimeString()}] CONTROLLER: Ready. Awaiting trigger signal.`
]);

const logTerminal = (msg: string) => {
  const timestamp = new Date().toLocaleTimeString();
  terminalLogs.value.push(`[${timestamp}] ${msg}`);
};

onUnmounted(() => {
  stopTimer();
});

async function launch(restart = false) {
  if (!challenge.value) return;
  errorMsg.value = "";
  flag.value = "";
  extendMsg.value = "";

  logTerminal(`INIT: Deploying ephemeral blockchain sandbox for challenge [id=${props.id}]${restart ? ' (REDEPLOY)' : ''}`);

  try {
    // Step 1: PoW
    state.value = "pow";
    powProgress.value = "Requesting PoW challenge...";
    logTerminal("SYS: Fetching Proof-of-Work challenge salt from launcher gateway...");
    const pow = await issuePow(props.id);
    logTerminal(`SYS: Received salt: "${pow.salt.substring(0, 12)}...". Prefix target: "${pow.zero_prefix}"`);

    powProgress.value = `Solving PoW (prefix: ${pow.zero_prefix})...`;
    logTerminal("SYS: Computing proof-of-work hash proof in local browser sandbox...");
    const solution = await solvePow(pow.salt, pow.zero_prefix);
    logTerminal(`SYS: Solution proof calculated: "${solution.substring(0, 16)}..."`);

    // Step 2: Submit PoW → get session
    state.value = "session";
    powProgress.value = "Verifying solution...";
    logTerminal("SYS: Dispatching validation proof payload to backend validator...");
    await submitPow(props.id, pow.challenge_token, solution);
    logTerminal("SYS: Validator validated payload. Spawning session token.");

    // Step 3: Start / Restart instance
    state.value = "launching";
    powProgress.value = restart ? "Restarting instance..." : "Launching instance...";
    logTerminal("SYS: Orchestrator sending deploy configurations to Docker Compose backend...");
    const inst = await startChallenge(props.id, restart);
    instance.value = inst;
    state.value = "active";
    powProgress.value = "";

    logTerminal(`SUCCESS: Sandbox environment initialized and verified.`);
    logTerminal(`RPC ENDPOINT: http://localhost:${inst.rpc_port || 8545}`);
    logTerminal(`DEPLOYED CONTRACT SETUP: ${inst.deploy_address}`);
    startTimer();
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : "Launch failed";
    errorMsg.value = errMsg;
    state.value = "error";
    powProgress.value = "";
    logTerminal(`ERROR: Orchestration service reported failure: ${errMsg}`);
  }
}

async function handleCheck() {
  if (!instance.value || checking.value) return;
  checking.value = true;
  errorMsg.value = "";
  logTerminal("SYS: Triggering solution state verification on-chain...");
  try {
    const res = await checkChallenge(props.id);
    if (res.solved && res.flag) {
      flag.value = res.flag;
      logTerminal(`SUCCESS: Validation verification completed. FLAG RECOVERED: ${res.flag}`);
    } else {
      const msg = res.message || "Not solved yet.";
      errorMsg.value = msg;
      state.value = "error";
      logTerminal(`WARNING: Verification failed. Setup conditions not met: "${msg}"`);
    }
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : "Verification failed";
    errorMsg.value = errMsg;
    state.value = "error";
    logTerminal(`ERROR: On-chain client execution failure: ${errMsg}`);
  } finally {
    checking.value = false;
  }
}

async function handleExtend() {
  if (!instance.value || extending.value) return;
  extending.value = true;
  extendMsg.value = "";
  errorMsg.value = "";
  logTerminal("SYS: Requesting lease duration extension from node daemon...");
  try {
    const res = await extendChallenge(props.id);
    if (res.status === "success") {
      if (instance.value) {
        instance.value.expires_at = res.expires_at;
        startTimer();
      }
      extendMsg.value = `Instance extended successfully!`;
      logTerminal(`SUCCESS: Lease timeline updated. Expiry reset.`);
    }
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : "Extension failed";
    errorMsg.value = errMsg;
    state.value = "error";
    logTerminal(`ERROR: Extension request denied by supervisor: ${errMsg}`);
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
  <div class="mx-auto max-w-6xl space-y-6 px-6 py-8 lg:px-8">
    <div>
      <button
        @click="router.push({ name: 'challenges' })"
        class="inline-flex items-center gap-2 rounded-full border border-border/60 bg-surface/40 px-3 py-2 text-sm text-text-muted transition-all duration-150 hover:border-border-hover hover:bg-surface/70 hover:text-text"
      >
        <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
        <span>Back to challenges</span>
      </button>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-24">
      <svg class="h-4 w-4 animate-spin text-accent" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>

    <div
      v-else-if="!challenge"
      class="rounded-2xl border border-danger/15 bg-danger-dim p-6 text-center"
    >
      <p class="text-sm font-medium text-danger">Challenge not found</p>
      <p class="mt-2 font-mono text-xs text-text-muted">{{ errorMsg }}</p>
    </div>

    <template v-else>
      <section class="animate-slide-up rounded-2xl border border-border/60 bg-gradient-to-br from-surface/60 to-surface/25 p-6 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]">
        <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div class="min-w-0 flex-1 space-y-4">
            <div class="flex flex-wrap items-center gap-3">
              <h1 class="text-2xl font-semibold tracking-tight text-text">
                {{ challenge.name || challenge.id }}
              </h1>
              <span
                v-if="challenge.category"
                class="inline-flex items-center rounded-full border border-border/50 bg-surface-2/80 px-2.5 py-1 font-mono text-[10px] font-medium uppercase tracking-wider text-text-muted"
              >
                {{ challenge.category }}
              </span>
            </div>

            <p class="max-w-3xl text-sm leading-relaxed text-text-muted">
              {{ challenge.description || "Deploy and interact with this challenge's smart contract environment." }}
            </p>

            <div class="flex flex-wrap items-center gap-2">
              <span v-if="challenge.chain_family" class="inline-flex items-center rounded-full border border-border/40 bg-surface-2/50 px-2.5 py-1 font-mono text-[11px] text-text-muted">
                {{ challenge.chain_family }}
              </span>
              <span v-if="challenge.chain_id" class="inline-flex items-center rounded-full border border-border/40 bg-surface-2/50 px-2.5 py-1 font-mono text-[11px] text-text-muted">
                Chain {{ challenge.chain_id }}
              </span>
              <span v-if="challenge.protocol" class="inline-flex items-center rounded-full border border-border/40 bg-surface-2/50 px-2.5 py-1 font-mono text-[11px] text-text-muted">
                {{ challenge.protocol }}
              </span>
            </div>
          </div>

          <div class="flex-shrink-0">
            <span
              class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 font-mono text-[11px] font-medium uppercase tracking-wider"
              :class="[
                stateColor,
                state === 'active'
                  ? 'border-ok/20 bg-ok-dim'
                  : state === 'error'
                    ? 'border-danger/20 bg-danger-dim'
                    : isLaunching
                      ? 'border-warn/20 bg-warn-dim'
                      : 'border-border bg-surface',
              ]"
            >
              <span v-if="isLaunching" class="h-1.5 w-1.5 rounded-full bg-current animate-pulse"></span>
              <span v-else-if="state === 'active'" class="h-1.5 w-1.5 rounded-full bg-ok"></span>
              {{ stateLabel }}
            </span>
          </div>
        </div>
      </section>

      <section class="grid gap-5 animate-slide-up lg:grid-cols-[340px,minmax(0,1fr)]" style="animation-delay: 50ms; animation-fill-mode: backwards">
        <div class="flex flex-col justify-between rounded-2xl border border-border/60 bg-surface/35 p-5 shadow-sm">
          <div class="space-y-3">
            <div v-if="powProgress" class="flex items-start gap-2 rounded-xl border border-border/40 bg-surface/70 p-3 font-mono text-xs text-text-muted">
              <svg class="h-3.5 w-3.5 shrink-0 animate-spin text-warn" viewBox="0 0 24 24" fill="none">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span class="leading-relaxed">{{ powProgress }}</span>
            </div>

            <div v-if="errorMsg && (state === 'error' || state === 'active')" class="rounded-xl border border-danger/15 bg-danger-dim p-3 font-mono text-xs text-danger">
              {{ errorMsg }}
            </div>

            <div v-if="flag" class="rounded-xl border border-ok/15 bg-ok-dim p-4">
              <p class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ok">Solved</p>
              <pre class="cursor-pointer select-all truncate rounded-lg border border-ok/15 bg-bg/60 p-2.5 font-mono text-xs text-emerald-300">{{ flag }}</pre>
            </div>

            <div v-if="extendMsg" class="rounded-xl border border-accent/15 bg-accent-dim p-3 font-mono text-xs text-accent">
              {{ extendMsg }}
            </div>
          </div>

          <div class="mt-5 space-y-2">
            <button
              v-if="instance"
              @click="handleCheck"
              :disabled="checking || isLaunching"
              class="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-ok/20 bg-emerald-600 px-4 py-3 text-sm font-semibold text-white transition-all duration-150 hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <svg v-if="checking" class="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {{ checking ? "Checking..." : "Check Solution" }}
            </button>

            <button
              v-if="instance"
              @click="copyFullEnv"
              class="inline-flex w-full items-center justify-center rounded-xl border border-border/60 bg-surface px-4 py-3 text-sm font-medium text-text-muted transition-all duration-150 hover:border-border-hover hover:bg-surface-2 hover:text-text"
            >
              Copy Solver Env
            </button>

            <button
              @click="launch(false)"
              :disabled="isLaunching"
              class="inline-flex w-full items-center justify-center gap-2 rounded-xl border px-4 py-3 text-sm font-semibold transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-50"
              :class="
                state === 'active'
                  ? 'border-border/60 bg-surface text-text-muted hover:border-border-hover hover:bg-surface-2 hover:text-text'
                  : 'border-transparent bg-accent text-black hover:bg-accent-hover'
              "
            >
              {{ state === 'active' ? 'Deploy Fresh' : 'Start Challenge' }}
            </button>

            <div v-if="instance" class="grid grid-cols-2 gap-2">
              <button
                @click="handleExtend"
                :disabled="extending || isLaunching || secondsLeft > (instance.extend_threshold_seconds || 300)"
                class="inline-flex items-center justify-center gap-2 rounded-xl border px-3 py-3 text-sm font-medium transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-40"
                :class="
                  secondsLeft > (instance.extend_threshold_seconds || 300)
                    ? 'border-border/60 bg-surface text-text-muted'
                    : 'border-accent/20 bg-accent/8 text-accent hover:bg-accent/15'
                "
                :title="secondsLeft > (instance.extend_threshold_seconds || 300) ? `Locked until under ${Math.round((instance.extend_threshold_seconds || 300) / 60)}m` : 'Extend lease'"
              >
                <svg v-if="extending" class="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span>Extend +{{ Math.round((instance.extend_seconds || 300) / 60) }}m</span>
              </button>

              <button
                @click="launch(true)"
                :disabled="isLaunching"
                class="inline-flex items-center justify-center rounded-xl border border-danger/20 bg-danger/8 px-3 py-3 text-sm font-medium text-danger transition-all duration-150 hover:bg-danger/15 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Reset State
              </button>
            </div>
          </div>
        </div>

        <div class="flex min-h-[360px] flex-col overflow-hidden rounded-2xl border border-border/60 bg-terminal-bg shadow-sm">
          <div class="flex items-center justify-between border-b border-border/30 bg-surface/20 px-4 py-3">
            <span class="text-xs font-mono font-medium tracking-wide text-text-muted">Terminal</span>
            <div class="flex items-center gap-1.5">
              <span class="h-2 w-2 rounded-full bg-emerald-500/80"></span>
              <span class="text-[10px] font-mono uppercase tracking-[0.18em] text-text-muted/50">live</span>
            </div>
          </div>

          <div class="flex-1 overflow-y-auto px-4 py-4 font-mono text-[11px] text-terminal-text">
            <div v-for="(log, idx) in terminalLogs" :key="idx" class="whitespace-pre-wrap leading-6 select-text">
              <span class="text-accent/70">{{ log.substring(0, 10) }}</span>
              <span class="ml-0.5 text-text-muted/80">{{ log.substring(10) }}</span>
            </div>
          </div>

          <div class="border-t border-border/20 px-4 py-2.5 font-mono text-[11px] text-text-muted/40">
            Extend retains contract state · Reset tears down and redeploys
          </div>
        </div>
      </section>

      <section
        v-if="instance"
        class="animate-slide-up rounded-2xl border border-border/60 bg-surface/35 p-6 shadow-sm"
        style="animation-delay: 100ms; animation-fill-mode: backwards"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-sm font-semibold text-text">Instance Credentials</h2>
          <span
            v-if="instance.expires_at"
            class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] transition-all duration-300"
            :class="secondsLeft < (instance.extend_threshold_seconds || 300) ? 'bg-danger-dim text-danger border-danger/20 animate-pulse-soft' : 'bg-surface-2 text-text-muted border-border/40'"
          >
            {{ timeLeftStr ? `${timeLeftStr}` : 'Expired' }}
          </span>
        </div>

        <div class="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div class="space-y-2 rounded-xl border border-border/50 bg-surface/30 p-4">
            <span class="text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">RPC Endpoint</span>
            <CopyField label="RPC URL" :value="rpcUrl" />
          </div>

          <div class="space-y-2 rounded-xl border border-border/50 bg-surface/30 p-4">
            <span class="text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">Private Key</span>
            <CopyField label="Private Key" :value="instance.private_key" />
          </div>

          <div class="space-y-2 rounded-xl border border-border/50 bg-surface/30 p-4">
            <span class="text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">Setup Contract</span>
            <CopyField label="Setup Address" :value="setupAddr" />
          </div>

          <div v-if="instance.wallet_address" class="space-y-2 rounded-xl border border-border/50 bg-surface/30 p-4">
            <span class="text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">Wallet Address</span>
            <CopyField label="Wallet" :value="instance.wallet_address" />
          </div>
        </div>

        <div class="mt-5 rounded-xl border border-border/50 bg-terminal-bg/80 p-4">
          <div class="mb-3 flex items-center justify-between gap-3">
            <span class="text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">Solver Environment</span>
            <button
              @click="copyFullEnv"
              class="text-[11px] font-medium text-accent transition-colors hover:text-accent-hover"
            >
              Copy
            </button>
          </div>
          <pre class="overflow-x-auto select-all rounded-lg border border-border/40 bg-bg/40 p-3 font-mono text-[11px] leading-relaxed text-terminal-text">{{ envBlock }}</pre>
        </div>
      </section>
    </template>
  </div>
</template>
