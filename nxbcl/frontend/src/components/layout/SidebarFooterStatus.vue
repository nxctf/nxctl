<script setup lang="ts">
const props = defineProps<{ online: boolean }>();
</script>

<template>
  <div class="px-4 py-3 border-t border-border flex items-center gap-2">
    <span class="w-1.5 h-1.5 rounded-full" :class="props.online ? 'bg-emerald-400' : 'bg-red-400'"></span>
    <span class="text-[11px] text-text-muted font-medium">{{ props.online ? 'Connected' : 'Offline' }}</span>
  </div>
</template>
