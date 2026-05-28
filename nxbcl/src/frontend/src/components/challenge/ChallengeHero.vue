<script setup lang="ts">
import type { Challenge, ChallengeState } from '../../types.js';
import StatusBadge from '../ui/StatusBadge.vue';

defineProps<{
  challenge: Challenge;
  stateLabel: string;
  state: ChallengeState;
  stateColor: string;
  isLaunching: boolean;
}>();
</script>

<template>
  <section class="rounded-2xl border border-border/60 bg-linear-to-br from-surface/60 to-surface/25 p-6 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]">
    <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
      <div class="min-w-0 flex-1 space-y-4">
        <div class="flex flex-wrap items-center gap-3">
          <h1 class="text-2xl font-semibold tracking-tight text-text">
            {{ challenge.name || challenge.id }}
          </h1>
          <span
            v-if="challenge.category"
            class="inline-flex items-center rounded-full border border-border/50 bg-surface-2/80 px-2.5 py-1 font-mono text-[10px] font-medium uppercase tracking-wider text-text-muted"
          >
            {{ challenge.category }}
          </span>
        </div>

        <p class="max-w-3xl text-sm leading-relaxed text-text-muted">
          {{ challenge.description || "Deploy and interact with this challenge's smart contract environment." }}
        </p>

        <div class="flex flex-wrap items-center gap-2">
          <span v-if="challenge.chain_family" class="inline-flex items-center rounded-full border border-border/40 bg-surface-2/50 px-2.5 py-1 font-mono text-[11px] text-text-muted">
            {{ challenge.chain_family }}
          </span>
          <span v-if="challenge.chain_id" class="inline-flex items-center rounded-full border border-border/40 bg-surface-2/50 px-2.5 py-1 font-mono text-[11px] text-text-muted">
            Chain {{ challenge.chain_id }}
          </span>
          <span v-if="challenge.protocol" class="inline-flex items-center rounded-full border border-border/40 bg-surface-2/50 px-2.5 py-1 font-mono text-[11px] text-text-muted">
            {{ challenge.protocol }}
          </span>
        </div>
      </div>

      <div class="shrink-0">
        <StatusBadge :status="state === 'idle' ? 'ready' : state" />
      </div>
    </div>
  </section>
</template>
