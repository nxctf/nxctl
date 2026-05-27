import type { Challenge, InstanceInfo, PowChallenge } from "./types.js";

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
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

export function issuePow(challengeId: string, userId: string): Promise<PowChallenge> {
  return request<PowChallenge>(`/api/challenges/${challengeId}/pow/challenge`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
    headers: { "X-User-Id": userId },
  });
}

export function submitPow(
  challengeId: string,
  userId: string,
  token: string,
  solution: string,
): Promise<{ status: string; session_id: string; expires_in: number }> {
  return request(`/api/challenges/${challengeId}/pow/solution`, {
    method: "POST",
    body: JSON.stringify({
      challenge_token: token,
      solution,
      user_id: userId,
    }),
    headers: { "X-User-Id": userId },
  });
}

export function startChallenge(
  challengeId: string,
  userId: string,
  restart = false,
): Promise<InstanceInfo> {
  const path = restart
    ? `/api/challenges/${challengeId}/restart`
    : `/api/challenges/${challengeId}/start`;
  return request<InstanceInfo>(path, {
    method: "POST",
    headers: { "X-User-Id": userId },
  });
}
