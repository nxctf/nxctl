<script setup lang="ts">
import type { PropType } from 'vue';
const props = defineProps<{
  instances: Array<any>;
  formatTimeLeft: (iso: string | null) => string;
}>();
</script>

<template>
  <div v-if="props.instances && props.instances.length" class="mt-3 px-3 py-2.5 rounded-md bg-surface/40">
    <div class="flex items-center justify-between mb-1.5">
      <span class="text-[12px] font-medium text-text-muted">Active Instances</span>
    </div>
    <div class="space-y-2 max-h-48 overflow-auto">
      <div v-for="inst in props.instances" :key="inst.instance_id" class="flex items-center justify-between gap-3">
        <div class="flex flex-col min-w-0">
          <span class="text-[12px] font-medium truncate max-w-36">{{ inst.challenge_id }}</span>
          <span class="text-[11px] text-text-muted font-mono truncate max-w-40">{{ inst.wallet_address }}</span>
        </div>
        <div class="text-right ml-2 shrink-0">
          <div class="text-[11px] font-mono text-accent/80">{{ props.formatTimeLeft(inst.expires_at) }}</div>
          <div class="text-[10px] text-text-muted">{{ inst.status }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
