export interface Challenge {
  id: string;
  name?: string;
  kind?: string;
  description?: string;
  chain_id?: number;
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
}
