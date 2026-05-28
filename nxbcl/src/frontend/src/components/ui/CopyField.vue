<script setup lang="ts">
import { ref } from "vue";
import { copyToClipboard } from "../../utils/clipboard";

defineProps<{
  label: string;
  value: string;
  mono?: boolean;
}>();

const copied = ref(false);

async function copy(text: string) {
  try {
    await copyToClipboard(text);
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
  <div>
    <div class="group flex items-stretch overflow-hidden rounded-xl border border-border/60 bg-terminal-bg/85 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-border-hover hover:shadow-[0_0_0_1px_var(--color-glow-accent)]">
      <code
        class="min-w-0 flex-1 px-3 py-2.5 text-sm text-terminal-text leading-relaxed break-all select-all"
        :class="mono !== false ? 'font-mono' : 'font-sans'"
      >
        {{ value }}
      </code>
      <button
        class="flex-shrink-0 inline-flex w-11 items-center justify-center border-l border-border/60 bg-transparent text-text-muted cursor-pointer transition-all duration-150 hover:bg-surface-2 hover:text-accent"
        :class="copied ? '!text-ok !bg-ok-dim' : ''"
        :aria-label="copied ? `${label} copied` : `Copy ${label}`"
        :title="copied ? 'Copied!' : `Copy ${label}`"
        @click="copy(value)"
      >
        <svg
          v-if="!copied"
          class="h-3.5 w-3.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
        <svg
          v-else
          class="h-3.5 w-3.5"
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
