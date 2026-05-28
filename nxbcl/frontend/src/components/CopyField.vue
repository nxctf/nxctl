<script setup lang="ts">
import { ref } from "vue";

defineProps<{
  label: string;
  value: string;
  mono?: boolean;
}>();

const copied = ref(false);

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 1500);
  } catch {
    /* clipboard API may not be available */
  }
}
</script>

<template>
  <div class="mb-2.5">
    <div class="mb-1 text-text-muted text-[11px] font-bold uppercase tracking-wide">
      {{ label }}
    </div>
    <div class="flex items-stretch border border-border rounded-lg bg-terminal-bg overflow-hidden">
      <code
        class="flex-1 px-3 py-2.5 text-terminal-text text-xs leading-relaxed break-all select-all"
        :class="mono !== false ? 'font-mono' : 'font-sans'"
      >
        {{ value }}
      </code>
      <button
        class="flex-shrink-0 flex items-center justify-center w-10 border-l border-border bg-white/[0.03] text-text-muted cursor-pointer transition-all duration-200 hover:bg-white/[0.08] hover:text-accent"
        :class="copied ? '!text-ok !bg-ok-dim/30' : ''"
        :title="copied ? 'Copied!' : 'Copy'"
        @click="copy(value)"
      >
        <!-- Copy icon -->
        <svg
          v-if="!copied"
          class="w-3.5 h-3.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
        <!-- Check icon -->
        <svg
          v-else
          class="w-3.5 h-3.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </button>
    </div>
  </div>
</template>
