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
  <div class="max-w-6xl mx-auto px-4 sm:px-6 py-8">
    <!-- Page header -->
    <div class="mb-8 animate-fade-in">
      <h2 class="text-2xl sm:text-3xl font-bold text-text mb-2">Challenges</h2>
      <p class="text-text-muted text-sm">
        Select a challenge to begin. Each challenge runs on a shared EVM chain with per-user
        isolation.
      </p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-24">
      <div class="flex items-center gap-3 text-text-muted">
        <svg class="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
          <circle
            class="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            stroke-width="4"
          />
          <path
            class="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <span class="text-sm font-medium">Loading challenges...</span>
      </div>
    </div>

    <!-- Error -->
    <div
      v-else-if="error"
      class="glass rounded-xl p-6 border-danger/30 bg-danger-dim/20 animate-fade-in"
    >
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-danger flex-shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
        <div>
          <p class="text-danger font-semibold text-sm">Failed to load challenges</p>
          <p class="text-text-muted text-xs mt-1">{{ error }}</p>
        </div>
      </div>
    </div>

    <!-- Empty -->
    <div
      v-else-if="!challenges.length"
      class="glass rounded-xl p-12 text-center animate-fade-in"
    >
      <div
        class="w-14 h-14 mx-auto mb-4 rounded-xl bg-surface-2 flex items-center justify-center"
      >
        <svg class="w-7 h-7 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
        </svg>
      </div>
      <p class="text-text-muted font-medium">No challenges found</p>
      <p class="text-text-muted/60 text-xs mt-1">
        Run <code class="text-accent">nxbcl sync</code> to pull challenges from the repo.
      </p>
    </div>

    <!-- Challenge Grid -->
    <div
      v-else
      class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
    >
      <router-link
        v-for="(challenge, idx) in challenges"
        :key="challenge.id"
        :to="{ name: 'challenge-detail', params: { id: challenge.id } }"
        class="group glass rounded-xl p-5 no-underline transition-all duration-300 hover:border-border-hover hover:shadow-lg hover:shadow-glow-accent hover:-translate-y-0.5 animate-slide-up"
        :style="{ animationDelay: `${idx * 60}ms`, animationFillMode: 'backwards' }"
      >
        <!-- Top row -->
        <div class="flex items-start justify-between gap-3 mb-3">
          <div class="flex-1 min-w-0">
            <h3 class="text-base font-bold text-text group-hover:text-accent transition-colors truncate">
              {{ challenge.name || challenge.id }}
            </h3>
            <p class="text-xs text-text-muted font-mono mt-0.5 truncate">
              {{ challenge.id }}
            </p>
          </div>

          <!-- Category pill -->
          <span
            v-if="challenge.category || challenge.kind"
            class="flex-shrink-0 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-gradient-to-r text-white/90"
            :class="categoryColor(challenge.category)"
          >
            {{ challenge.category || challenge.kind }}
          </span>
        </div>

        <!-- Description -->
        <p class="text-sm text-text-muted leading-relaxed line-clamp-2 mb-4">
          {{ challenge.description || "Blockchain challenge" }}
        </p>

        <!-- Footer meta -->
        <div class="flex items-center gap-3 text-[11px] text-text-muted/70">
          <span v-if="challenge.chain_family" class="flex items-center gap-1">
            <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M13.73 21a2 2 0 01-3.46 0M18.63 13A17.89 17.89 0 0118 8M6 13a18 18 0 01-.63-5" />
              <circle cx="12" cy="5" r="3" />
            </svg>
            {{ challenge.chain_family?.toUpperCase() }}
          </span>
          <span v-if="challenge.chain_id" class="flex items-center gap-1">
            <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
              <path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16" />
            </svg>
            Chain {{ challenge.chain_id }}
          </span>
        </div>

        <!-- Hover arrow -->
        <div class="mt-4 pt-3 border-t border-border/50 flex items-center justify-between">
          <span class="text-xs font-semibold text-accent/70 group-hover:text-accent transition-colors">
            Open Challenge
          </span>
          <svg
            class="w-4 h-4 text-text-muted/40 group-hover:text-accent group-hover:translate-x-0.5 transition-all"
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
