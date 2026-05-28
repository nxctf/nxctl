<script setup lang="ts">
import SidebarActiveInstances from './SidebarActiveInstances.vue';
import SidebarServiceStatus from './SidebarServiceStatus.vue';
import SidebarFooterStatus from './SidebarFooterStatus.vue';
const props = defineProps<{ services: any; online: boolean; rpcStatus: string; rpcTimeLeftStr: string | null; rpcExpiresAt: string | null; formatTimeLeft: (iso: string | null) => string }>();
</script>

<template>
  <aside class="w-full md:w-60 md:fixed md:top-0 md:left-0 md:h-screen border-b md:border-b-0 md:border-r border-border bg-bg flex flex-col shrink-0 z-30">
    <div class="h-14 border-b border-border flex items-center px-5">
      <router-link to="/challenges" class="flex items-center gap-2.5 no-underline group">
        <div class="w-6 h-6 rounded-md bg-accent/15 flex items-center justify-center text-accent font-semibold text-[10px] tracking-tight">NX</div>
        <span class="text-sm font-semibold tracking-tight text-text">NXBCL</span>
      </router-link>
    </div>

    <nav class="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
      <router-link to="/challenges" class="flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] font-medium no-underline transition-all duration-150" :class="$route.name === 'challenges' || $route.name === 'challenge-detail' ? 'bg-surface text-text' : 'text-text-muted hover:text-text hover:bg-surface/50'">
        <svg class="w-4 h-4 shrink-0 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
        <span>Challenges</span>
      </router-link>

      <SidebarServiceStatus :online="props.online" :rpcStatus="props.rpcStatus" :rpcTimeLeftStr="props.rpcTimeLeftStr" :rpcExpiresAt="props.rpcExpiresAt" />

      <SidebarActiveInstances :instances="props.services.active_instances || []" :formatTimeLeft="props.formatTimeLeft" />
    </nav>

    <SidebarFooterStatus :online="props.online" />
  </aside>
</template>
