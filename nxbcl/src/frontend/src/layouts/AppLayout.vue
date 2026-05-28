<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue';
import AppSidebar from '../components/layout/AppSidebar.vue';
import AppTopbar from '../components/layout/AppTopbar.vue';
import { checkHealth, getRpcStatus, startRpc, stopRpc, extendRpc } from '../api.js';
import { getServices } from '../api.js';

const online = ref(false);
const rpcStatus = ref('stopped');
const rpcUrl = ref('http://localhost:8545');
const isToggling = ref(false);
const showRpcControl = ref(false);

const rpcExpiresAt = ref<string | null>(null);
const rpcSecondsLeft = ref<number>(999999);
const rpcTimeLeftStr = ref<string>('');

const isExtendingRpc = ref(false);
const rpcExtendThresholdSeconds = ref(600);
const rpcExtendSeconds = ref(600);

const updateRpcCountdown = () => {
  if (!rpcExpiresAt.value) {
    rpcSecondsLeft.value = 999999;
    rpcTimeLeftStr.value = '';
    return;
  }
  const expiry = new Date(rpcExpiresAt.value).getTime();
  const now = new Date().getTime();
  const diff = Math.max(0, Math.floor((expiry - now) / 1000));
  rpcSecondsLeft.value = diff;
  if (diff === 0) {
    rpcTimeLeftStr.value = 'Expired';
    rpcStatus.value = 'stopped';
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
    online.value = h.status === 'ok';
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
    rpcStatus.value = 'stopped';
    rpcExpiresAt.value = null;
  }
};

let intervalId: any = null;
let rpcTimerId: any = null;
const services = ref<any>({ anvil: null, panel: null, active_instances: [] });

async function fetchServices() {
  try {
    const s = await getServices();
    services.value = s || { anvil: null, panel: null, active_instances: [] };
  } catch (e) {
    services.value = { anvil: null, panel: null, active_instances: [] };
  }
}

const formatTimeLeft = (iso: string | null) => {
  if (!iso) return '';
  const expiry = new Date(iso).getTime();
  const now = new Date().getTime();
  const diff = Math.max(0, Math.floor((expiry - now) / 1000));
  if (diff === 0) return 'Expired';
  const m = Math.floor(diff / 60);
  const s = diff % 60;
  return `${m}:${s < 10 ? '0' : ''}${s}`;
};

onMounted(async () => {
  await updateStatus();
  await fetchServices();
  intervalId = setInterval(updateStatus, 5000);
  setInterval(fetchServices, 5000);
  rpcTimerId = setInterval(updateRpcCountdown, 1000);
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
  if (rpcTimerId) clearInterval(rpcTimerId);
});

const handleStartRpc = async () => {
  if (isToggling.value) return;
  isToggling.value = true;
  rpcStatus.value = 'starting';
  try {
    const res = await startRpc();
    if (res.status === 'success') {
      rpcStatus.value = 'running';
      rpcExpiresAt.value = res.expires_at || null;
      rpcExtendThresholdSeconds.value = res.extend_threshold_seconds || rpcExtendThresholdSeconds.value;
      rpcExtendSeconds.value = res.extend_seconds || rpcExtendSeconds.value;
      if (res.rpc_url) rpcUrl.value = res.rpc_url;
      updateRpcCountdown();
    } else {
      rpcStatus.value = 'stopped';
      alert('Failed to start RPC: ' + (res.error || 'unknown error'));
    }
  } catch (err: any) {
    rpcStatus.value = 'stopped';
    alert('Error: ' + err.message);
  } finally {
    isToggling.value = false;
    await updateStatus();
  }
};

const handleRestartRpc = async () => {
  if (isToggling.value) return;
  if (!confirm('Warning: Restarting the Shared RPC will reset the local blockchain. All active challenge instances, factories, and player progress will be cleared! Are you sure?')) return;
  isToggling.value = true;
  rpcStatus.value = 'stopping';
  try {
    await stopRpc();
    rpcStatus.value = 'starting';
    const res = await startRpc();
    if (res.status === 'success') {
      rpcStatus.value = 'running';
      rpcExpiresAt.value = res.expires_at || null;
      rpcExtendThresholdSeconds.value = res.extend_threshold_seconds || rpcExtendThresholdSeconds.value;
      rpcExtendSeconds.value = res.extend_seconds || rpcExtendSeconds.value;
      if (res.rpc_url) rpcUrl.value = res.rpc_url;
      updateRpcCountdown();
    } else {
      rpcStatus.value = 'stopped';
      alert('Failed to start RPC: ' + (res.error || 'unknown error'));
    }
  } catch (err: any) {
    rpcStatus.value = 'stopped';
    alert('Error: ' + err.message);
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
    if (res.status === 'success') {
      rpcExpiresAt.value = res.expires_at;
      updateRpcCountdown();
    }
  } catch (err: any) {
    alert('Error: ' + err.message);
  } finally {
    isExtendingRpc.value = false;
  }
};

</script>

<template>
  <div class="min-h-screen bg-bg text-text font-sans antialiased flex flex-col md:flex-row overflow-x-hidden">
    <AppSidebar :services="services" :online="online" :rpcStatus="rpcStatus" :rpcTimeLeftStr="rpcTimeLeftStr" :rpcExpiresAt="rpcExpiresAt" :formatTimeLeft="formatTimeLeft" />
    <div class="flex-1 flex flex-col min-w-0 md:ml-60">
      <AppTopbar :pageTitle="$route.name === 'challenges' ? 'Challenges' : String($route.params.id || 'Challenge')" :rpcStatus="rpcStatus" :rpcUrl="rpcUrl" :rpcExpiresAt="rpcExpiresAt" :rpcTimeLeftStr="rpcTimeLeftStr" :rpcSecondsLeft="rpcSecondsLeft" :rpcExtendThresholdSeconds="rpcExtendThresholdSeconds" :rpcExtendSeconds="rpcExtendSeconds" :isToggling="isToggling" :isExtendingRpc="isExtendingRpc" @start-rpc="handleStartRpc" @restart-rpc="handleRestartRpc" @extend-rpc="handleExtendRpc" />

      <main class="flex-1 overflow-y-auto md:pt-14">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>
