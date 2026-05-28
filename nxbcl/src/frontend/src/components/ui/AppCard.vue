<script setup lang="ts">
defineProps<{
  hoverable?: boolean;
}>();
</script>

<template>
  <div
    class="rounded-2xl border border-border bg-surface/35 shadow-sm transition-all duration-200"
    :class="{
      'hover:-translate-y-0.5 hover:border-border-hover hover:bg-surface/55 hover:shadow-[0_0_0_1px_var(--color-glow-accent)] cursor-pointer': hoverable
    }"
  >
    <div v-if="$slots.header" class="border-b border-border/30 px-5 py-4">
      <slot name="header" />
    </div>
    <div class="px-5 py-5">
      <slot />
    </div>
  </div>
</template>
