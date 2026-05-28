<script setup lang="ts">
const props = defineProps<{ to: string; label: string }>();
</script>

<template>
  <router-link
    :to="props.to"
    class="flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] font-medium no-underline transition-all duration-150"
    :class="$route.path.startsWith(props.to) ? 'bg-surface text-text' : 'text-text-muted hover:text-text hover:bg-surface/50'"
  >
    <slot />
    <span>{{ props.label }}</span>
  </router-link>
</template>
