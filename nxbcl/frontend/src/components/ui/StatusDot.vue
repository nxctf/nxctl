<script setup lang="ts">
import { computed } from 'vue';
const props = defineProps<{ status: string }>();

const statusClass = computed(() => {
  if (props.status === 'running') return 'bg-emerald-400';
  if (props.status === 'stopped') return 'bg-zinc-500';
  return 'bg-amber-400 animate-pulse';
});
</script>

<template>
  <span :class="statusClass" class="w-2.5 h-2.5 rounded-full inline-block"></span>
</template>
