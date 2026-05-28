<script setup lang="ts">
import CredentialCard from './CredentialCard.vue';
import EnvBlock from '../ui/EnvBlock.vue';

defineProps<{
  instance: any;
  rpcUrl: string;
  setupAddr: string;
  envBlock: string;
  timeLeftStr: string;
  secondsLeft: number;
}>();
</script>

<template>
  <section class="flex h-full flex-col rounded-2xl border border-border/60 bg-surface/35 p-6 shadow-sm">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border/30 pb-4">
      <h2 class="text-sm font-semibold text-text">Instance Credentials</h2>
      <span
        v-if="instance.expires_at"
        class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] transition-all duration-300"
        :class="secondsLeft < (instance.extend_threshold_seconds || 300) ? 'bg-danger-dim text-danger border-danger/20 animate-pulse-soft' : 'bg-surface-2 text-text-muted border-border/40'"
      >
        {{ timeLeftStr ? `${timeLeftStr}` : 'Expired' }}
      </span>
    </div>

    <div class="mt-5 flex-1 space-y-3">
      <CredentialCard label="RPC_URL" :value="rpcUrl" copyLabel="RPC endpoint" />
      <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
        <CredentialCard v-if="instance.chain_id" label="CHAIN_ID" :value="String(instance.chain_id)" copyLabel="Chain ID" />
        <CredentialCard v-if="instance.wallet_address" label="WALLET_ADDRESS" :value="instance.wallet_address" copyLabel="Wallet address" />
      </div>
      <CredentialCard label="SETUP_ADDR" :value="setupAddr" copyLabel="Setup contract" />
      <CredentialCard label="PRIVKEY" :value="instance.private_key" copyLabel="Private key" sensitive />
    </div>

    <div class="mt-5">
      <EnvBlock :content="envBlock" />
    </div>
  </section>
</template>
