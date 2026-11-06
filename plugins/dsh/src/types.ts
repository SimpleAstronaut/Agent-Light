export interface Config {
  enabled?: boolean;
  endpoint: string;
  tokenFile: string;
  dataDir: string;
  requestTimeoutMs?: number;
  activityIntervalMs?: number;
  maxSpoolBytes?: number;
}
export interface Draft {
  type: string;
  session_id?: string;
  instance_id?: string;
  turn_id?: string | null;
  turn_seq?: number;
  attention_id?: string | null;
  reason_code?: string | null;
  outcome?: string;
  live_instances?: string[];
}
