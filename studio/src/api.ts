import type { Issue } from './types';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly issues: Issue[] = [],
  ) {
    super(message);
  }
}

async function send<T>(path: string, signal: AbortSignal, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { signal, ...init });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new ApiError(
      'Studio cannot reach the local server. Check that puzzlepress-studio is running, then retry.',
      'unavailable',
    );
  }
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as {
      error?: { message: string; code: string; issues: Issue[] };
    } | null;
    throw new ApiError(
      data?.error?.message ?? 'The server could not complete this request. Try again.',
      data?.error?.code ?? 'server_error',
      data?.error?.issues,
    );
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      'Studio received an unreadable response. Retry or reload the saved source to review.',
      'malformed_response',
    );
  }
}

export function request<T>(path: string, signal: AbortSignal, body?: object): Promise<T> {
  return send<T>(
    path,
    signal,
    body
      ? {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      : {},
  );
}

// The one non-JSON request: a photograph's original bytes for cover import.
export function upload<T>(path: string, signal: AbortSignal, file: Blob, type: string) {
  return send<T>(path, signal, { method: 'POST', headers: { 'Content-Type': type }, body: file });
}
