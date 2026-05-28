<script setup lang="ts">
import RpcControlDropdown from '../rpc/RpcControlDropdown.vue';
const props = defineProps<{
  pageTitle: string;
  rpcStatus: string;
  rpcUrl: string;
  rpcExpiresAt: string | null;
  rpcTimeLeftStr: string | null;
  rpcSecondsLeft: number;
  rpcExtendThresholdSeconds: number;
  rpcExtendSeconds: number;
  isToggling: boolean;
  isExtendingRpc: boolean;
}>();
const emit = defineEmits(['start-rpc','restart-rpc','extend-rpc']);
</script>

<template>
  <header class="h-14 border-b border-border bg-bg/80 backdrop-blur-sm flex items-center justify-between px-6 sticky top-0 md:fixed md:top-0 md:left-60 md:right-0 z-40">
    <div class="flex items-center gap-2 text-sm">
      <span class="text-text-muted">{{ pageTitle }}</span>
    </div>
    <div class="flex items-center gap-3">
      <RpcControlDropdown
        :rpcStatus="props.rpcStatus"
        :rpcUrl="props.rpcUrl"
        :rpcExpiresAt="props.rpcExpiresAt"
        :rpcTimeLeftStr="props.rpcTimeLeftStr"
        :rpcSecondsLeft="props.rpcSecondsLeft"
        :rpcExtendThresholdSeconds="props.rpcExtendThresholdSeconds"
        :rpcExtendSeconds="props.rpcExtendSeconds"
        :isToggling="props.isToggling"
        :isExtendingRpc="props.isExtendingRpc"
        @start-rpc="$emit('start-rpc')"
        @restart-rpc="$emit('restart-rpc')"
        @extend-rpc="$emit('extend-rpc')"
      />
    </div>
  </header>
</template>
