<script setup lang="ts">
import { ref } from 'vue';
import CopyButton from './CopyButton.vue';
const props = defineProps<{
  label: string;
  value: string;
  copyLabel?: string;
  sensitive?: boolean;
}>();

const copied = ref(false);

async function copyValue() {
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
    setTimeout(() => (copied.value = false), 1500);
  } catch {
    // noop
  }
}

function onIconCopied() {
  copied.value = true;
  setTimeout(() => (copied.value = false), 1500);
}
</script>

<template>
  <div class="group">
    <div
      role="button"
      tabindex="0"
      @click="copyValue"
      @keyup.enter.prevent="copyValue"
      class="min-w-0 flex items-center justify-between gap-3 overflow-hidden rounded-xl border border-border/60 bg-surface/45 p-3.5 transition-all duration-150 hover:border-accent/20 hover:bg-surface/55 hover:shadow-[0_0_0_1px_var(--color-glow-accent)] cursor-pointer"
    >
      <div class="min-w-0">
        <div class="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted mb-1">{{ props.label }}</div>
        <div class="font-mono text-[12px] text-text truncate overflow-hidden whitespace-nowrap leading-5" :title="props.value">
          {{ props.value }}
        </div>
      </div>
      <div class="flex items-center">
        <CopyButton :value="props.value" :label="props.copyLabel || props.label" @copied="onIconCopied" />
      </div>
    </div>
  </div>
</template>
