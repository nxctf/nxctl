<script setup lang="ts">
import { ref } from 'vue';
import { copyToClipboard } from '../../utils/clipboard';

const props = defineProps<{ content: string }>();
const copied = ref(false);

async function copyEnv() {
  try {
    await copyToClipboard(props.content);
    copied.value = true;
    setTimeout(() => (copied.value = false), 1500);
  } catch {
    // noop
  }
}
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between gap-3">
      <div class="text-[11px] font-medium uppercase tracking-[0.16em] text-text-muted">Solver Environment</div>
      <span v-if="copied" class="text-[10px] text-ok font-medium transition-all duration-300">Copied!</span>
      <span v-else class="text-[10px] text-text-muted/60 font-medium">Click block to copy</span>
    </div>
    <pre
      @click="copyEnv"
      class="overflow-x-auto whitespace-pre-wrap select-all rounded-lg border border-border/40 bg-bg/40 p-4 font-mono text-[11px] leading-relaxed text-terminal-text cursor-copy transition-all duration-150 hover:bg-bg/60 hover:border-accent/30"
      v-text="props.content"
    ></pre>
  </div>
</template>
