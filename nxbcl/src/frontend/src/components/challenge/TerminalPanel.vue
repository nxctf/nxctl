<script setup lang="ts">
defineProps<{
  logs: string[];
}>();
</script>

<template>
  <section class="flex h-full flex-col overflow-hidden rounded-2xl border border-border/60 bg-terminal-bg shadow-sm">
    <div class="flex items-center justify-between border-b border-border/30 bg-surface/20 px-4 py-3">
      <span class="text-xs font-mono font-medium tracking-wide text-text-muted">Terminal</span>
    </div>

    <div class="flex-1 overflow-y-auto px-4 py-4 font-mono text-[11px] text-terminal-text">
      <div v-for="(log, idx) in logs" :key="idx" class="whitespace-pre-wrap leading-6 select-text">
        <span class="text-accent/70">{{ log.substring(0, 10) }}</span>
        <span class="ml-0.5 text-text-muted/80">{{ log.substring(10) }}</span>
      </div>
    </div>
  </section>
</template>
