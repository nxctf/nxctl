export interface Challenge {
  id: string;
  name?: string;
  kind?: string;
  category?: string;
  description?: string;
  chain_id?: number;
  chain_family?: string;
  protocol?: string;
  rpc_internal?: string;
  runtime?: {
    type?: string;
    scope?: string;
  };
  solver?: {
    file?: string;
    env?: string[];
  };
}

export interface PowChallenge {
  challenge_token: string;
  salt: string;
  zero_prefix: string;
}
export interface InstanceInfo {
  instance_id: string;
  wallet_address: string;
  private_key: string;
  deploy_address?: string;
  setup_address?: string;
  rpc_url?: string;
  rpc_port?: number;
  chain_id?: number;
  status: string;
  expires_at?: string;
  extend_threshold_seconds?: number;
  extend_seconds?: number;
}
export type ChallengeState =
  | "idle"
  | "starting"
  | "pow"
  | "session"
  | "launching"
  | "active"
  | "solved"
  | "error";
