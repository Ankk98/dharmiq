import { ApiError } from "@/lib/api";

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
