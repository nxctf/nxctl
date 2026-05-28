<script setup lang="ts">
import { ref } from 'vue';
const props = defineProps<{ value: string; label?: string; className?: string }>();
const emits = defineEmits(['copied']);
const copied = ref(false);

async function doCopy(e: Event) {
  e.stopPropagation();
  try {
    const text = props.value || '';
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', 'true');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    copied.value = true;
    emits('copied');
    setTimeout(() => (copied.value = false), 1500);
  } catch {
    // noop
  }
}
</script>

<template>
  <button
    @click="doCopy"
    :aria-label="props.label ? `Copy ${props.label}` : 'Copy'"
    :title="copied ? 'Copied!' : (props.label ? `Copy ${props.label}` : 'Copy')"
    class="inline-flex items-center justify-center min-w-9 min-h-9 p-2 rounded-md border border-border/60 bg-transparent text-text-muted hover:bg-surface-2 hover:text-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
  >
    <svg v-if="!copied" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
    <svg v-else class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  </button>
</template>
