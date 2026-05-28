<script setup lang="ts">
import { onMounted, ref } from "vue";
import { listChallenges } from "../api.js";
import type { Challenge } from "../types.js";

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

function categoryColor(cat?: string): string {
  switch (cat?.toLowerCase()) {
    case "blockchain":
      return "from-accent to-emerald-500";
    case "web":
      return "from-blue-400 to-indigo-500";
    case "crypto":
      return "from-purple-400 to-pink-500";
    case "pwn":
      return "from-red-400 to-orange-500";
    default:
      return "from-gray-400 to-gray-500";
  }
}
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
    <div
      v-else-if="!challenges.length"
      class="rounded-2xl border border-border/60 border-dashed bg-surface/20 p-16 text-center animate-fade-in"
    >
      <div class="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-border/60 bg-surface/70">
        <svg class="h-4 w-4 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
          <path d="M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
        </svg>
      </div>
      <p class="text-sm font-medium text-text">No challenges found</p>
      <p class="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-text-muted">
        Run <code class="rounded bg-accent-dim px-1.5 py-0.5 font-mono text-[12px] text-accent">nxbcl sync</code> to pull challenge configurations.
      </p>
    </div>

    <!-- Challenge Grid -->
    <div
      v-else
      class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <router-link
        v-for="(challenge, idx) in challenges"
        :key="challenge.id"
        :to="{ name: 'challenge-detail', params: { id: challenge.id } }"
        class="group flex flex-col justify-between rounded-2xl border border-border/60 bg-surface/55 p-6 no-underline transition-all duration-200 hover:-translate-y-0.5 hover:border-border-hover hover:bg-surface/75 hover:shadow-[0_0_0_1px_var(--color-glow-accent)] animate-slide-up"
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
      </router-link>
    </div>
  </div>
</template>
