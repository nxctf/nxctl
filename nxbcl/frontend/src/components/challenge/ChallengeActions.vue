<script setup lang="ts">
import AppCard from '../ui/AppCard.vue';
import InfraButton from '../ui/InfraButton.vue';

defineProps<{
  powProgress: string;
  errorMsg: string;
  flag: string;
  extendMsg: string;
  instance: any | null;
  isLaunching: boolean;
  checking: boolean;
  extending: boolean;
  secondsLeft: number;
  state: string;
  extendThresholdSeconds: number;
  extendSeconds: number;
}>();

defineEmits<{
  (e: 'check'): void;
  (e: 'launch'): void;
  (e: 'extend'): void;
  (e: 'reset'): void;
}>();
</script>

<template>
  <div class="grid grid-cols-1 gap-6" :class="instance ? 'xl:grid-cols-[minmax(0,1.2fr)_minmax(340px,1fr)]' : 'grid-cols-1'">
    <!-- Left Card: Control Panel -->
    <AppCard class="flex flex-col justify-center min-h-[130px]">
      <!-- Start/Launch Button when not running -->
      <InfraButton
        v-if="!instance"
        @click="$emit('launch')"
        :disabled="isLaunching"
        variant="primary"
        class="w-full !py-3.5"
      >
        Start Challenge
      </InfraButton>

      <!-- Active Instance Actions -->
      <div v-else class="space-y-3">
        <InfraButton
          @click="$emit('check')"
          :disabled="checking || isLaunching"
          variant="success"
          :loading="checking"
          class="w-full !py-3.5"
        >
          Check Solution
        </InfraButton>

        <div class="grid grid-cols-2 gap-3">
          <InfraButton
            @click="$emit('extend')"
            :disabled="extending || isLaunching || secondsLeft > (instance.extend_threshold_seconds || 300)"
            :variant="secondsLeft > (instance.extend_threshold_seconds || 300) ? 'secondary' : 'primary'"
            :loading="extending"
            class="!py-3"
            :title="secondsLeft > (instance.extend_threshold_seconds || 300) ? `Locked until under ${Math.round((instance.extend_threshold_seconds || 300) / 60)}m` : 'Extend lease'"
          >
            Extend +{{ Math.round((instance.extend_seconds || 300) / 60) }}m
          </InfraButton>

          <InfraButton
            @click="$emit('reset')"
            :disabled="isLaunching"
            variant="danger"
            class="!py-3"
          >
            Reset State
          </InfraButton>
        </div>
      </div>
    </AppCard>

    <!-- Right Card: Output / Console Feed -->
    <AppCard class="flex flex-col justify-center min-h-[130px]">
      <div class="flex-1 flex flex-col justify-center">
        <!-- Default State when no output message yet -->
        <div v-if="!powProgress && !errorMsg && !flag && !extendMsg" class="flex flex-1 items-center justify-center rounded-xl border border-dashed border-border/30 bg-surface/10 px-4 py-6 text-center text-xs font-mono text-text-muted/50 h-full min-h-[90px]">
          Awaiting execution signals...
        </div>

        <div v-if="powProgress" class="flex items-center justify-center gap-2 rounded-xl border border-border/40 bg-surface/70 p-4 font-mono text-xs text-text-muted w-full h-full min-h-[90px]">
          <svg class="h-4 w-4 shrink-0 animate-spin text-warn" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span class="leading-relaxed">{{ powProgress }}</span>
        </div>

        <div v-if="errorMsg && (state === 'error' || state === 'active')" class="flex flex-col justify-center rounded-xl border border-danger/15 bg-danger-dim p-3.5 font-mono text-xs text-danger w-full h-full min-h-[90px]">
          <p class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-danger/70">Error Message</p>
          <span class="leading-relaxed">{{ errorMsg }}</span>
        </div>

        <div v-if="flag" class="flex flex-col justify-center rounded-xl border border-ok/15 bg-ok-dim p-3.5 w-full h-full min-h-[90px]">
          <p class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ok">Solved Flag</p>
          <pre class="cursor-pointer select-all truncate rounded-lg border border-ok/15 bg-bg/60 p-2 font-mono text-xs text-emerald-300 w-full">{{ flag }}</pre>
        </div>

        <div v-if="extendMsg" class="flex flex-col justify-center rounded-xl border border-accent/15 bg-accent-dim p-3.5 font-mono text-xs text-accent w-full h-full min-h-[90px]">
          {{ extendMsg }}
        </div>
      </div>
    </AppCard>
  </div>
</template>
