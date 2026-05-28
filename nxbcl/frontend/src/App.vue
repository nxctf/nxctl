<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { checkHealth, getRpcStatus, startRpc, stopRpc, extendRpc } from "./api.js";

const online = ref(false);
const rpcStatus = ref("stopped");
const rpcUrl = ref("http://localhost:8545");
const isToggling = ref(false);
const showRpcControl = ref(false);

const rpcExpiresAt = ref<string | null>(null);
const rpcSecondsLeft = ref<number>(999999);
const rpcTimeLeftStr = ref<string>("");

const isExtendingRpc = ref(false);
const rpcExtendThresholdSeconds = ref(600);
const rpcExtendSeconds = ref(600);

const updateRpcCountdown = () => {
  if (!rpcExpiresAt.value) {
    rpcSecondsLeft.value = 999999;
    rpcTimeLeftStr.value = "";
    return;
  }
  const expiry = new Date(rpcExpiresAt.value).getTime();
  const now = new Date().getTime();
  const diff = Math.max(0, Math.floor((expiry - now) / 1000));
  rpcSecondsLeft.value = diff;

  if (diff === 0) {
    rpcTimeLeftStr.value = "Expired";
    rpcStatus.value = "stopped";
    rpcExpiresAt.value = null;
    return;
  }

  const m = Math.floor(diff / 60);
  const s = diff % 60;
  rpcTimeLeftStr.value = `${m}:${s < 10 ? '0' : ''}${s}`;
};

const updateStatus = async () => {
  try {
    const h = await checkHealth();
    online.value = h.status === "ok";
  } catch {
    online.value = false;
  }

  try {
    const r = await getRpcStatus();
    rpcStatus.value = r.status;
    rpcUrl.value = r.rpc_url;
    rpcExpiresAt.value = (r as any).expires_at || null;
    rpcExtendThresholdSeconds.value = (r as any).extend_threshold_seconds || 600;
    rpcExtendSeconds.value = (r as any).extend_seconds || 600;
  } catch {
    rpcStatus.value = "stopped";
    rpcExpiresAt.value = null;
  }
};

let intervalId: any = null;
let rpcTimerId: any = null;

onMounted(async () => {
  await updateStatus();
  intervalId = setInterval(updateStatus, 5000);
  rpcTimerId = setInterval(updateRpcCountdown, 1000);
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
  if (rpcTimerId) clearInterval(rpcTimerId);
});

const handleStartRpc = async () => {
  if (isToggling.value) return;
  isToggling.value = true;
  rpcStatus.value = "starting";
  try {
    const res = await startRpc();
    if (res.status === "success") {
      rpcStatus.value = "running";
    } else {
      rpcStatus.value = "stopped";
      alert("Failed to start RPC: " + (res.error || "unknown error"));
    }
  } catch (err: any) {
    rpcStatus.value = "stopped";
    alert("Error: " + err.message);
  } finally {
    isToggling.value = false;
    await updateStatus();
  }
};

const handleRestartRpc = async () => {
  if (isToggling.value) return;
  if (!confirm("Warning: Restarting the Shared RPC will reset the local blockchain. All active challenge instances, factories, and player progress will be cleared! Are you sure?")) return;
  isToggling.value = true;
  rpcStatus.value = "stopping";
  try {
    await stopRpc();
    rpcStatus.value = "starting";
    const res = await startRpc();
    if (res.status === "success") {
      rpcStatus.value = "running";
    } else {
      rpcStatus.value = "stopped";
      alert("Failed to start RPC: " + (res.error || "unknown error"));
    }
  } catch (err: any) {
    rpcStatus.value = "stopped";
    alert("Error: " + err.message);
  } finally {
    isToggling.value = false;
    await updateStatus();
  }
};

const handleExtendRpc = async () => {
  if (isExtendingRpc.value) return;
  isExtendingRpc.value = true;
  try {
    const res = await extendRpc();
    if (res.status === "success") {
      rpcExpiresAt.value = res.expires_at;
      updateRpcCountdown();
    }
  } catch (err: any) {
    alert("Error: " + err.message);
  } finally {
    isExtendingRpc.value = false;
  }
};
</script>
<template>
  <div class="min-h-screen bg-bg text-text font-sans antialiased flex flex-col md:flex-row overflow-x-hidden">

    <!-- Sidebar Navigation -->
    <aside class="w-full md:w-60 border-b md:border-b-0 md:border-r border-border bg-bg flex flex-col shrink-0">

      <!-- Brand Header -->
      <div class="h-14 border-b border-border flex items-center px-5">
        <router-link to="/challenges" class="flex items-center gap-2.5 no-underline group">
          <div class="w-6 h-6 rounded-md bg-accent/15 flex items-center justify-center text-accent font-semibold text-[10px] tracking-tight group-hover:bg-accent/25 transition-colors duration-200">
            NX
          </div>
          <span class="text-sm font-semibold tracking-tight text-text">NXBCL</span>
        </router-link>
      </div>

      <!-- Navigation Links -->
      <nav class="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">

        <router-link
          to="/challenges"
          class="flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] font-medium no-underline transition-all duration-150"
          :class="$route.name === 'challenges' || $route.name === 'challenge-detail' ? 'bg-surface text-text' : 'text-text-muted hover:text-text hover:bg-surface/50'"
        >
          <svg class="w-4 h-4 shrink-0 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.75">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          <span>Challenges</span>
        </router-link>

        <!-- Divider -->
        <div class="pt-5 pb-2 px-3">
          <span class="text-[11px] font-medium text-text-muted/50 uppercase tracking-wider">Services</span>
        </div>

        <!-- Shared RPC Node Status Item -->
        <div class="px-3 py-2.5 rounded-md bg-surface/40">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[12px] font-medium text-text-muted">Anvil Node</span>
            <span class="w-1.5 h-1.5 rounded-full" :class="rpcStatus === 'running' ? 'bg-emerald-400' : rpcStatus === 'stopped' ? 'bg-zinc-500' : 'bg-amber-400 animate-pulse'"></span>
          </div>
          <span class="text-[11px] font-mono text-text-muted/60 capitalize">{{ rpcStatus }}</span>
          <div v-if="rpcStatus === 'running' && rpcExpiresAt" class="text-[11px] font-mono text-accent/80 mt-1">
            {{ rpcTimeLeftStr || 'Calculating...' }}
          </div>
        </div>
      </nav>

      <!-- Sidebar Footer / API Indicator -->
      <div class="px-4 py-3 border-t border-border flex items-center gap-2">
        <span class="w-1.5 h-1.5 rounded-full" :class="online ? 'bg-emerald-400' : 'bg-red-400'"></span>
        <span class="text-[11px] text-text-muted font-medium">
          {{ online ? 'Connected' : 'Offline' }}
        </span>
      </div>
    </aside>

    <!-- Main Workspace Area -->
    <div class="flex-1 flex flex-col min-w-0">

      <!-- Top header bar -->
      <header class="h-14 border-b border-border bg-bg/80 backdrop-blur-sm flex items-center justify-between px-6 sticky top-0 z-40">

        <!-- Breadcrumb / Page Title -->
        <div class="flex items-center gap-2 text-sm">
          <span class="text-text-muted">{{ $route.name === 'challenge-detail' ? 'Challenges' : '' }}</span>
          <span v-if="$route.name === 'challenge-detail'" class="text-text-muted/40">/</span>
          <span class="text-text font-medium">{{ $route.name === 'challenges' ? 'Challenges' : $route.params.id || 'Challenge' }}</span>
        </div>

        <!-- RPC Controls -->
        <div class="flex items-center gap-3">

          <!-- Shared RPC Status Dropdown Button -->
          <div class="relative">
            <button
              @click="showRpcControl = !showRpcControl"
              class="inline-flex items-center gap-2 text-[13px] font-medium px-3 py-1.5 rounded-md border border-border bg-surface hover:bg-surface-2 text-text-muted hover:text-text transition-all duration-150 cursor-pointer"
            >
              <span class="w-1.5 h-1.5 rounded-full" :class="{
                'bg-emerald-400': rpcStatus === 'running',
                'bg-amber-400 animate-pulse': rpcStatus === 'starting' || rpcStatus === 'stopping',
                'bg-zinc-500': rpcStatus === 'stopped'
              }"></span>
              <span>RPC</span>
              <svg class="w-3 h-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            <!-- Dropdown Menu -->
            <div
              v-if="showRpcControl"
              class="absolute right-0 mt-2 w-72 bg-surface border border-border rounded-lg shadow-2xl shadow-black/40 p-4 z-50 text-left animate-fade-in"
            >
              <div class="flex justify-between items-center mb-3">
                <h3 class="text-[13px] font-semibold text-text">Shared Anvil RPC</h3>
                <button @click="showRpcControl = false" class="text-text-muted hover:text-text text-xs cursor-pointer bg-transparent border-none p-1 rounded hover:bg-surface-2 transition-colors">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
              </div>

              <div class="space-y-3">
                <div class="flex items-center justify-between text-[12px] pb-2.5 border-b border-border/50">
                  <span class="text-text-muted">Endpoint</span>
                  <code class="text-accent/90 bg-accent-dim px-1.5 py-0.5 rounded text-[11px] font-mono">{{ rpcUrl }}</code>
                </div>

                <div v-if="rpcStatus === 'running' && rpcExpiresAt" class="flex items-center justify-between text-[12px] pb-2.5 border-b border-border/50">
                  <span class="text-text-muted">Time Left</span>
                  <span
                    class="font-mono font-medium px-1.5 py-0.5 rounded text-[11px]"
                    :class="rpcSecondsLeft < rpcExtendThresholdSeconds ? 'bg-danger-dim text-danger' : 'bg-surface-2 text-text-muted'"
                  >
                    {{ rpcTimeLeftStr || 'Calculating...' }}
                  </span>
                </div>

                <!-- Control Buttons -->
                <div class="flex flex-col gap-2 pt-0.5">
                  <div class="flex gap-2">
                    <button
                      v-if="rpcStatus === 'stopped'"
                      @click="handleStartRpc"
                      :disabled="isToggling"
                      class="flex-1 text-center py-2 px-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold rounded-md text-[12px] transition duration-150 cursor-pointer border-none"
                    >
                      {{ isToggling ? "Starting..." : "Start RPC" }}
                    </button>
                    <button
                      v-if="rpcStatus === 'running'"
                      @click="handleRestartRpc"
                      :disabled="isToggling"
                      class="flex-1 text-center py-2 px-3 bg-danger/10 text-danger border border-danger/20 hover:bg-danger/15 disabled:opacity-50 font-semibold rounded-md text-[12px] transition duration-150 cursor-pointer"
                    >
                      {{ isToggling ? "Restarting..." : "Restart" }}
                    </button>
                    <button
                      v-if="rpcStatus === 'starting' || rpcStatus === 'stopping'"
                      disabled
                      class="flex-1 text-center py-2 px-3 bg-warn-dim text-warn font-semibold rounded-md text-[12px] border border-warn/15"
                    >
                      Transitioning...
                    </button>
                  </div>

                  <!-- Extend RPC Button -->
                  <button
                    v-if="rpcStatus === 'running' && rpcExpiresAt"
                    @click="handleExtendRpc"
                    :disabled="isExtendingRpc || rpcSecondsLeft > rpcExtendThresholdSeconds"
                    class="w-full text-center py-2 px-3 rounded-md text-[12px] font-semibold border transition-all duration-200 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-1.5"
                    :class="
                      rpcSecondsLeft > rpcExtendThresholdSeconds
                        ? 'border-border bg-surface-2 text-text-muted cursor-not-allowed'
                        : 'border-accent/20 bg-accent/8 text-accent hover:bg-accent/15'
                    "
                    :title="rpcSecondsLeft > rpcExtendThresholdSeconds ? `Only extendable when under ${Math.round(rpcExtendThresholdSeconds / 60)} minutes left!` : 'Extend RPC lease'"
                  >
                    <svg v-if="isExtendingRpc" class="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <span>Extend +{{ Math.round(rpcExtendSeconds / 60) }}m</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      <!-- Main workspace content -->
      <main class="flex-1 overflow-y-auto">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>
<style scoped>
.page-enter-active,
.page-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-3px);
}
</style>
