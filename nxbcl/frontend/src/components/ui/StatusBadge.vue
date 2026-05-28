<script setup lang="ts">
defineProps<{
  status: string;
}>();

function badgeClasses(s: string): string {
  switch (s) {
    case "active":
    case "running":
    case "solved":
      return "border-ok/40 text-ok bg-ok-dim/30";
    case "pow":
    case "session":
    case "launching":
    case "starting":
      return "border-warn/40 text-warn bg-warn-dim/30";
    case "error":
      return "border-danger/40 text-danger bg-danger-dim/30";
    default:
      return "border-border text-text-muted bg-surface-2/50";
  }
}

function dotClasses(s: string): string {
  switch (s) {
    case "active":
    case "running":
    case "solved":
      return "bg-ok shadow-[0_0_6px_var(--color-ok)] animate-pulse-soft";
    case "pow":
    case "session":
    case "launching":
    case "starting":
      return "bg-warn shadow-[0_0_6px_var(--color-warn)] animate-pulse-soft";
    case "error":
      return "bg-danger shadow-[0_0_6px_var(--color-danger)]";
    default:
      return "bg-text-muted";
  }
}
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 border rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide whitespace-nowrap"
    :class="badgeClasses(status)"
  >
    <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" :class="dotClasses(status)"></span>
    {{ status }}
  </span>
</template>
