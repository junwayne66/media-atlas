import { api } from "./client";

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export function getHealth(): Promise<HealthResponse> {
  return api.get<HealthResponse>("/healthz", undefined);
}
