async function sha256Hex(value: string): Promise<string> {
  const encoded = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function solvePow(salt: string, zeroPrefix: string): Promise<string> {
  let nonce = 0;
  while (true) {
    const solution = String(nonce);
    const hash = await sha256Hex(salt + solution);
    if (hash.startsWith(zeroPrefix)) {
      return solution;
    }
    nonce += 1;
    if (nonce % 500 === 0) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  }
}
