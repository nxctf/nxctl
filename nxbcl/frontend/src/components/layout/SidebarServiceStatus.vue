<script setup lang="ts">
const props = defineProps<{ online: boolean; rpcStatus: string; rpcTimeLeftStr: string | null; rpcExpiresAt: string | null }>();
</script>

<template>
  <div class="px-3 py-2.5">
    <div class="text-[11px] font-medium text-text-muted/50 uppercase tracking-wider mb-2">Services</div>
    <div class="space-y-2">
      <div class="flex items-center justify-between text-[13px] font-medium">
        <div class="text-text-muted">Anvil</div>
        <div class="font-mono text-[13px]" :class="props.rpcStatus === 'running' ? 'text-emerald-400' : props.rpcStatus === 'stopped' ? 'text-zinc-500' : 'text-amber-400'">{{ props.rpcStatus }}</div>
      </div>
      <div v-if="props.rpcExpiresAt" class="flex items-center justify-between text-[13px] font-medium">
        <div class="text-text-muted">TTL</div>
        <div class="font-mono text-[13px] text-accent">{{ props.rpcTimeLeftStr }}</div>
      </div>
    </div>
  </div>
</template>
