<script setup lang="ts">
// defineProps / defineEmits are compiler macros in <script setup>
const props = defineProps<{
  rpcStatus: string;
  rpcUrl: string;
  rpcExpiresAt: string | null;
  rpcTimeLeftStr: string | null;
  rpcSecondsLeft: number;
  rpcExtendThresholdSeconds: number;
  rpcExtendSeconds: number;
  isToggling: boolean;
  isExtendingRpc: boolean;
}>();
const emit = defineEmits(['start-rpc','restart-rpc','extend-rpc']);
import { ref } from 'vue';
const show = ref(false);

function onStart() { emit('start-rpc'); show.value = false; }
function onRestart() { emit('restart-rpc'); show.value = false; }
function onExtend() { emit('extend-rpc'); show.value = false; }
function toggle() { show.value = !show.value; }
</script>

<template>
  <div class="relative">
    <button @click="toggle" class="inline-flex items-center gap-2 text-[13px] font-medium px-3 py-1.5 rounded-md border border-border bg-surface hover:bg-surface-2 text-text-muted hover:text-text transition-all duration-150 cursor-pointer">
      <span class="w-1.5 h-1.5 rounded-full" :class="props.rpcStatus === 'running' ? 'bg-emerald-400' : props.rpcStatus === 'stopped' ? 'bg-zinc-500' : 'bg-amber-400 animate-pulse'"></span>
      <span>RPC</span>
      <svg class="w-3 h-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
    </button>
    <div v-if="show" class="absolute right-0 mt-2 w-72 bg-surface border border-border rounded-lg shadow-2xl shadow-black/40 p-4 z-50 text-left">
        <div class="flex justify-between items-center mb-3">
        <h3 class="text-[13px] font-semibold text-text">Shared Anvil RPC</h3>
        <button @click="show = false" class="text-text-muted hover:text-text text-xs cursor-pointer bg-transparent border-none p-1 rounded hover:bg-surface-2 transition-colors">Close</button>
      </div>
      <div class="space-y-3">
        <div class="flex items-center justify-between text-[12px] pb-2.5 border-b border-border/50">
          <span class="text-text-muted">Endpoint</span>
          <code class="text-accent/90 bg-accent-dim px-1.5 py-0.5 rounded text-[11px] font-mono block truncate max-w-56" :title="props.rpcUrl">{{ props.rpcUrl }}</code>
        </div>
        <div v-if="props.rpcStatus === 'running' && props.rpcExpiresAt" class="flex items-center justify-between text-[12px] pb-2.5 border-b border-border/50">
          <span class="text-text-muted">Time Left</span>
          <span class="font-mono font-medium px-1.5 py-0.5 rounded text-[11px]" :class="props.rpcSecondsLeft < props.rpcExtendThresholdSeconds ? 'bg-danger-dim text-danger' : 'bg-surface-2 text-text-muted'">{{ props.rpcTimeLeftStr }}</span>
        </div>
        <div class="flex flex-col gap-2 pt-0.5">
          <div class="flex gap-2">
            <button v-if="props.rpcStatus === 'stopped'" @click="onStart" :disabled="props.isToggling" class="flex-1 text-center py-2 px-3 bg-emerald-600 text-white font-semibold rounded-md text-[12px]">Start RPC</button>
            <button v-if="props.rpcStatus === 'running'" @click="onRestart" :disabled="props.isToggling" class="flex-1 text-center py-2 px-3 bg-danger/10 text-danger border border-danger/20 rounded-md text-[12px]">Restart</button>
            <button v-if="props.rpcStatus === 'starting' || props.rpcStatus === 'stopping'" disabled class="flex-1 text-center py-2 px-3 bg-warn-dim text-warn rounded-md text-[12px]">Transitioning...</button>
          </div>
          <button v-if="props.rpcStatus === 'running' && props.rpcExpiresAt" @click="onExtend" :disabled="props.isExtendingRpc || props.rpcSecondsLeft > props.rpcExtendThresholdSeconds" class="w-full text-center py-2 px-3 rounded-md text-[12px] font-semibold border">Extend +{{ Math.round(props.rpcExtendSeconds / 60) }}m</button>
        </div>
      </div>
    </div>
  </div>
</template>
