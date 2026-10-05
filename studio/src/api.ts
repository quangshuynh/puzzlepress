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

export async function request<T>(path: string, signal: AbortSignal, body?: object): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      signal,
      ...(body
        ? {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          }
        : {}),
    });
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
