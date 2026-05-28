import { sha256 } from "js-sha256";

export async function solvePow(salt: string, zeroPrefix: string): Promise<string> {
  let nonce = 0;
  while (true) {
    const solution = String(nonce);
    const hash = sha256(salt + solution);
    if (hash.startsWith(zeroPrefix)) {
      return solution;
    }
    nonce += 1;
    if (nonce % 500 === 0) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  }
}
