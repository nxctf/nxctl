import type { Challenge, InstanceInfo, PowChallenge } from "./types.js";

function getUserId(): string {
  let uid = localStorage.getItem("nxbcl_uid");
  if (!uid) {
    uid =
      "u-" +
      crypto.randomUUID?.() ||
      Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("nxbcl_uid", uid);
  }
  return uid;
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const uid = getUserId();
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": uid,
      ...(options.headers || {}),
    },
    ...options,
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.detail || data.error || response.statusText);
  }
  return data as T;
}

export function listChallenges(): Promise<Challenge[]> {
  return request<Challenge[]>("/api/challenges");
}

export function getChallenge(challengeId: string): Promise<Challenge> {
  return request<Challenge>(`/api/challenges/${challengeId}`);
}

export function issuePow(challengeId: string): Promise<PowChallenge> {
  const uid = getUserId();
  return request<PowChallenge>(
    `/api/challenges/${challengeId}/pow/challenge`,
    {
      method: "POST",
      body: JSON.stringify({ user_id: uid }),
    },
  );
}

export function submitPow(
  challengeId: string,
  token: string,
  solution: string,
): Promise<{ status: string; session_id: string; expires_in: number }> {
  const uid = getUserId();
  return request(`/api/challenges/${challengeId}/pow/solution`, {
    method: "POST",
    body: JSON.stringify({
      challenge_token: token,
      solution,
      user_id: uid,
    }),
  });
}

export function startChallenge(
  challengeId: string,
  restart = false,
): Promise<InstanceInfo> {
  const path = restart
    ? `/api/challenges/${challengeId}/restart`
    : `/api/challenges/${challengeId}/start`;
  return request<InstanceInfo>(path, { method: "POST" });
}

export function getInstance(challengeId: string): Promise<InstanceInfo> {
  return request<InstanceInfo>(`/api/challenges/${challengeId}/instance`);
}

export function extendChallenge(
  challengeId: string,
): Promise<{ status: string; expires_at: string; expires_in: number }> {
  return request(`/api/challenges/${challengeId}/extend`, { method: "POST" });
}

export function checkChallenge(
  challengeId: string,
): Promise<{ solved: boolean; flag: string | null; message: string }> {
  return request(`/api/challenges/${challengeId}/check`, { method: "POST" });
}

export function checkHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/health");
}

export function getRpcStatus(): Promise<{ status: string; rpc_url: string }> {
  return request<{ status: string; rpc_url: string }>("/api/rpc/status");
}

export function startRpc(): Promise<{ status: string; error?: string }> {
  return request<{ status: string; error?: string }>("/api/rpc/start", { method: "POST" });
}

export function stopRpc(): Promise<{ status: string; error?: string }> {
  return request<{ status: string; error?: string }>("/api/rpc/stop", { method: "POST" });
}

export function extendRpc(): Promise<{ status: string; expires_at: string }> {
  return request<{ status: string; expires_at: string }>("/api/rpc/extend", { method: "POST" });
}
