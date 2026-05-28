<script setup lang="ts">
import { onMounted, ref } from "vue";
import { listChallenges } from "../api.js";
import type { Challenge } from "../types.js";
import AppCard from "../components/ui/AppCard.vue";
import EmptyState from "../components/ui/EmptyState.vue";

const challenges = ref<Challenge[]>([]);
const loading = ref(true);
const error = ref("");

onMounted(async () => {
  try {
    challenges.value = await listChallenges();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load challenges";
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="w-full max-w-none px-4 py-6 lg:px-8 xl:px-10">

   <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-24">
      <div class="flex items-center gap-3 text-text-muted">
        <svg class="h-4 w-4 animate-spin text-accent" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span class="text-sm">Loading challenges...</span>
      </div>
    </div>

    <!-- Error -->
    <div
      v-else-if="error"
      class="rounded-2xl border border-danger/15 bg-danger-dim p-5 animate-fade-in"
    >
      <p class="text-sm font-medium text-danger">Failed to load challenges</p>
      <p class="mt-2 rounded-lg border border-border/40 bg-bg/50 p-3 font-mono text-xs text-text-muted">{{ error }}</p>
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else-if="!challenges.length"
      title="No challenges found"
    >
      Run <code class="rounded bg-accent-dim px-1.5 py-0.5 font-mono text-[12px] text-accent">nxbcl sync</code> to pull challenge configurations.
    </EmptyState>

    <!-- Challenge Grid -->
    <div
      v-else
      class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <router-link
        v-for="(challenge, idx) in challenges"
        :key="challenge.id"
        :to="{ name: 'challenge-detail', params: { id: challenge.id } }"
        class="no-underline group"
      >
        <AppCard
          hoverable
          class="flex flex-col justify-between h-full !p-6 animate-slide-up"
          :style="{ animationDelay: `${idx * 40}ms`, animationFillMode: 'backwards' }"
        >
          <div class="space-y-4">
            <div class="flex items-start justify-between gap-3">
              <h3 class="text-base font-semibold tracking-tight text-text transition-colors group-hover:text-accent">
                {{ challenge.name || challenge.id }}
              </h3>
              <span
                v-if="challenge.category || challenge.kind"
                class="inline-flex flex-shrink-0 items-center rounded-full border border-border/50 bg-surface-2/80 px-2.5 py-1 font-mono text-[10px] font-medium uppercase tracking-wider text-text-muted transition-colors group-hover:border-accent/20 group-hover:text-accent"
              >
                {{ challenge.category || challenge.kind }}
              </span>
            </div>

            <p class="text-sm leading-relaxed text-text-muted line-clamp-3">
              {{ challenge.description || "Blockchain CTF sandbox environment." }}
            </p>
          </div>

          <div class="mt-5 flex items-center justify-between gap-3 border-t border-border/30 pt-4 text-xs text-text-muted/70">
            <div class="flex items-center gap-3 font-mono">
              <span v-if="challenge.chain_family" class="flex items-center gap-1.5">
                <span class="h-1.5 w-1.5 rounded-full bg-accent/60"></span>
                {{ challenge.chain_family?.toUpperCase() }}
              </span>
              <span v-if="challenge.chain_id">Chain {{ challenge.chain_id }}</span>
            </div>

            <svg
              class="h-4 w-4 text-text-muted/40 transition-all duration-200 group-hover:text-accent group-hover:translate-x-0.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </div>
        </AppCard>
      </router-link>
    </div>
  </div>
</template>
