<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { issuePow, listChallenges, startChallenge, submitPow, getInstance, extendChallenge, checkChallenge } from "../api.js";
import { solvePow } from "../pow.js";
import type { Challenge, ChallengeState, InstanceInfo } from "../types.js";
import ChallengeHero from "../components/challenge/ChallengeHero.vue";
import ChallengeActions from "../components/challenge/ChallengeActions.vue";
import TerminalPanel from "../components/challenge/TerminalPanel.vue";
import InstanceCredentialsPanel from "../components/challenge/InstanceCredentialsPanel.vue";

const props = defineProps<{ id: string }>();

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

let statusCheckCounter = 0;

const updateCountdown = async () => {
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
    state.value = "idle";
    instance.value = null;
    stopTimer();
    return;
  }

  const m = Math.floor(diff / 60);
  const s = diff % 60;
  timeLeftStr.value = `${m}:${s < 10 ? '0' : ''}${s}`;

  // Periodically verify instance existence on the backend (every 5 seconds)
  statusCheckCounter++;
  if (statusCheckCounter >= 5) {
    statusCheckCounter = 0;
    try {
      const activeInst = await getInstance(props.id);
      if (!activeInst || activeInst.status !== "running") {
        logTerminal("SYS: Ephemeral sandbox environment terminated. Reason: Blockchain RPC node is offline or stopped.");
        instance.value = null;
        state.value = "idle";
        stopTimer();
      }
    } catch {
      logTerminal("SYS: Ephemeral sandbox environment terminated. Reason: Blockchain RPC node is offline or stopped.");
      instance.value = null;
      state.value = "idle";
      stopTimer();
    }
  }
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
  <div class="w-full max-w-none space-y-6 px-4 py-6 lg:px-8 xl:px-10">
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
      <ChallengeHero
        :challenge="challenge"
        :stateLabel="stateLabel"
        :state="state"
        :stateColor="stateColor"
        :isLaunching="isLaunching"
      />

      <ChallengeActions
        :powProgress="powProgress"
        :errorMsg="errorMsg"
        :flag="flag"
        :extendMsg="extendMsg"
        :instance="instance"
        :isLaunching="isLaunching"
        :checking="checking"
        :extending="extending"
        :secondsLeft="secondsLeft"
        :state="state"
        :extendThresholdSeconds="instance?.extend_threshold_seconds || 300"
        :extendSeconds="instance?.extend_seconds || 300"
        @check="handleCheck"
        @launch="launch(false)"
        @extend="handleExtend"
        @reset="launch(true)"
      />

      <section
        class="grid gap-6"
        :class="instance ? 'xl:grid-cols-[minmax(0,1.2fr)_minmax(340px,1fr)] xl:items-stretch' : 'grid-cols-1'"
      >
        <TerminalPanel :logs="terminalLogs" class="h-full" />
        <InstanceCredentialsPanel
          v-if="instance"
          :instance="instance"
          :rpcUrl="rpcUrl"
          :setupAddr="setupAddr"
          :envBlock="envBlock"
          :timeLeftStr="timeLeftStr"
          :secondsLeft="secondsLeft"
          class="h-full"
        />
      </section>
    </template>
  </div>
</template>
