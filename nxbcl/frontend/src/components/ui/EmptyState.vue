<script setup lang="ts">
defineProps<{
  title: string;
}>();
</script>

<template>
  <div class="rounded-2xl border border-border/60 border-dashed bg-surface/20 p-16 text-center animate-fade-in">
    <div class="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-border/60 bg-surface/70">
      <slot name="icon">
        <svg class="h-4 w-4 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
          <path d="M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
        </svg>
      </slot>
    </div>
    <p class="text-sm font-medium text-text">{{ title }}</p>
    <div class="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-text-muted">
      <slot />
    </div>
  </div>
</template>
