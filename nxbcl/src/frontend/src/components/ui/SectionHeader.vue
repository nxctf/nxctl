<script setup lang="ts">
defineProps<{
  title: string;
}>();
</script>

<template>
  <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border/30 pb-4">
    <h2 class="text-sm font-semibold text-text tracking-tight uppercase">{{ title }}</h2>
    <div v-if="$slots.actions" class="flex items-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>
