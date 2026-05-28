<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { checkHealth, getRpcStatus, startRpc, stopRpc } from "./api.js";

const online = ref(false);
const rpcStatus = ref("stopped");
const rpcUrl = ref("http://localhost:8545");
const isToggling = ref(false);
const showRpcControl = ref(false);

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
  } catch {
    rpcStatus.value = "stopped";
  }
};

let intervalId: any = null;

onMounted(async () => {
  await updateStatus();
  intervalId = setInterval(updateStatus, 5000);
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
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

const handleStopRpc = async () => {
  if (isToggling.value) return;
  if (!confirm("Are you sure you want to stop the shared RPC container? This will affect any running challenge instances.")) return;
  isToggling.value = true;
  rpcStatus.value = "stopping";
  try {
    const res = await stopRpc();
    if (res.status === "success") {
      rpcStatus.value = "stopped";
    } else {
      alert("Failed to stop RPC: " + (res.error || "unknown error"));
    }
  } catch (err: any) {
    alert("Error: " + err.message);
  } finally {
    isToggling.value = false;
    await updateStatus();
  }
};
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <!-- Header -->
    <header class="glass border-b border-border sticky top-0 z-50">
      <div class="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <router-link to="/challenges" class="flex items-center gap-3 no-underline">
          <div
            class="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-emerald-600 flex items-center justify-center text-bg font-bold text-sm"
          >
            NX
          </div>
          <h1 class="text-lg font-bold text-text tracking-tight">
            NXBCL<span class="text-text-muted font-normal ml-1.5 hidden sm:inline"
              >Launcher</span
             >
          </h1>
        </router-link>

        <div class="flex items-center gap-3">
          <!-- API Status -->
          <span
            class="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full border border-border bg-card/50 text-text-muted"
            title="Launcher API status"
          >
            <span
              class="w-1.5 h-1.5 rounded-full"
              :class="online ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'"
            ></span>
            API: {{ online ? "Online" : "Offline" }}
          </span>

          <!-- Shared RPC Status & Control -->
          <div class="relative">
            <button
              @click="showRpcControl = !showRpcControl"
              class="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-card-hover text-text transition cursor-pointer"
            >
              <span
                class="w-2 h-2 rounded-full"
                :class="{
                  'bg-emerald-500 animate-pulse': rpcStatus === 'running',
                  'bg-amber-500 animate-pulse': rpcStatus === 'starting' || rpcStatus === 'stopping',
                  'bg-red-500': rpcStatus === 'stopped'
                }"
              ></span>
              RPC Node: <span class="capitalize font-bold" :class="{
                'text-emerald-400': rpcStatus === 'running',
                'text-amber-400': rpcStatus === 'starting' || rpcStatus === 'stopping',
                'text-red-400': rpcStatus === 'stopped'
              }">{{ rpcStatus }}</span>
              <svg class="w-3.5 h-3.5 text-text-muted ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            <!-- Dropdown Menu -->
            <div
              v-if="showRpcControl"
              class="absolute right-0 mt-2 w-64 bg-card border border-border rounded-xl shadow-2xl p-4 z-50 text-left"
            >
              <div class="flex justify-between items-start mb-1">
                <h3 class="text-sm font-bold text-text">Shared Blockchain RPC</h3>
                <button @click="showRpcControl = false" class="text-text-muted hover:text-text text-xs cursor-pointer">✕</button>
              </div>
              <p class="text-xs text-text-muted mb-3">
                Status controls for the local Ethereum (Anvil) network instance.
              </p>

              <div class="space-y-2.5">
                <div class="flex items-center justify-between text-xs border-b border-border/50 pb-2">
                  <span class="text-text-muted">RPC Endpoint</span>
                  <code class="text-accent bg-accent-dim/30 px-1 py-0.5 rounded text-[10px]">{{ rpcUrl }}</code>
                </div>

                <div class="flex gap-2">
                  <button
                    v-if="rpcStatus === 'stopped'"
                    @click="handleStartRpc"
                    :disabled="isToggling"
                    class="flex-1 text-center py-2 px-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold rounded-lg text-xs transition cursor-pointer"
                  >
                    {{ isToggling ? "Starting..." : "Start RPC" }}
                  </button>
                  <button
                    v-if="rpcStatus === 'running'"
                    @click="handleStopRpc"
                    :disabled="isToggling"
                    class="flex-1 text-center py-2 px-3 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white font-bold rounded-lg text-xs transition cursor-pointer"
                  >
                    {{ isToggling ? "Stopping..." : "Stop RPC" }}
                  </button>
                  <button
                    v-if="rpcStatus === 'starting' || rpcStatus === 'stopping'"
                    disabled
                    class="flex-1 text-center py-2 px-3 bg-amber-600/50 text-white font-bold rounded-lg text-xs transition"
                  >
                    Transitioning...
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </header>

    <!-- Main content -->
    <main class="flex-1">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- Footer -->
    <footer class="border-t border-border py-6 mt-auto">
      <div class="max-w-6xl mx-auto px-4 sm:px-6">
        <p class="text-xs text-text-muted text-center">
          NXBCL — Blockchain Challenge Launcher · NXCTF
        </p>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.page-enter-active,
.page-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
