<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'success' | 'infra';
  type?: 'button' | 'submit' | 'reset';
  disabled?: boolean;
  loading?: boolean;
}>(), {
  variant: 'secondary',
  type: 'button',
  disabled: false,
  loading: false,
});

const variantClasses = computed(() => {
  switch (props.variant) {
    case 'primary':
      return 'bg-accent hover:bg-accent-hover text-black border border-transparent font-semibold';
    case 'success':
      return 'bg-emerald-600 hover:bg-emerald-500 text-white border border-ok/20 font-semibold';
    case 'danger':
      return 'bg-danger/8 hover:bg-danger/15 text-danger border border-danger/20 font-medium';
    case 'infra':
      return 'bg-surface hover:bg-surface-2 text-text-muted hover:text-text border border-border';
    case 'ghost':
      return 'bg-transparent hover:bg-surface-2 text-text-muted hover:text-text border border-transparent';
    case 'secondary':
    default:
      return 'border border-border bg-surface hover:bg-surface-2 text-text-muted hover:text-text font-medium';
  }
});
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    class="inline-flex items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm transition-all duration-150 cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
    :class="variantClasses"
  >
    <svg v-if="loading" class="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
    <slot />
  </button>
</template>
