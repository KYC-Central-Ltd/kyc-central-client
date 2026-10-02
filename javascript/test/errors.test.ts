/** Status codes map onto the documented error classes. */

import { describe, expect, it } from 'vitest';

import type { APIStatusError } from '../src/index.js';
import {
  AuthenticationError,
  BadRequestError,
  KYCCentral,
  KYCCentralError,
  NotFoundError,
  PermissionDeniedError,
  RateLimitError,
  ServerError,
  ServiceUnavailableError,
  UnprocessableEntityError,
} from '../src/index.js';
import { BASE_URL, jsonResponse, mockFetch } from './helpers.js';

function clientWith(responses: Response[]): KYCCentral {
  return new KYCCentral({
    apiKey: 'k',
    baseUrl: BASE_URL,
    fetch: mockFetch(responses),
    maxRetries: 0,
  });
}

describe('status mapping', () => {
  it.each([
    [400, BadRequestError],
    [401, AuthenticationError],
    [403, PermissionDeniedError],
    [404, NotFoundError],
    [422, UnprocessableEntityError],
    [429, RateLimitError],
    [500, ServerError],
    [503, ServiceUnavailableError],
  ])('maps %i to the expected class', async (status, ExpectedClass) => {
    const client = clientWith([jsonResponse({ detail: 'nope' }, status)]);

    await expect(client.ruleSets.list()).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ExpectedClass);
      expect(error).toBeInstanceOf(KYCCentralError);
      const statusError = error as APIStatusError;
      expect(statusError.statusCode).toBe(status);
      expect(statusError.detail).toBe('nope');
      expect(statusError.message).toContain('nope');
      return true;
    });
  });

  it('preserves the error class name for logging', async () => {
    const client = clientWith([jsonResponse({ detail: 'nope' }, 404)]);
    await expect(client.ruleSets.list()).rejects.toMatchObject({ name: 'NotFoundError' });
  });
});

describe('error bodies', () => {
  it('exposes Retry-After on a rate limit error', async () => {
    const response = new Response(JSON.stringify({ detail: 'Rate limit exceeded' }), {
      status: 429,
      headers: { 'content-type': 'application/json', 'Retry-After': '30' },
    });
    const client = clientWith([response]);

    await expect(client.ruleSets.list()).rejects.toSatisfy((error: unknown) => {
      const rateLimit = error as RateLimitError;
      expect(rateLimit.retryAfter).toBe(30);
      // Header lookup stays case-insensitive, as HTTP header names are.
      expect(rateLimit.headers.get('retry-after')).toBe('30');
      return true;
    });
  });

  it('exposes Retry-After on a service unavailable error', async () => {
    const withHeader = clientWith([
      new Response('{"detail":"down"}', {
        status: 503,
        headers: { 'content-type': 'application/json', 'Retry-After': '300' },
      }),
    ]);
    await expect(withHeader.ruleSets.list()).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ServiceUnavailableError);
      expect((error as ServiceUnavailableError).retryAfter).toBe(300);
      return true;
    });

    const without = clientWith([jsonResponse({ detail: 'down' }, 503)]);
    await expect(without.ruleSets.list()).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ServiceUnavailableError);
      expect((error as ServiceUnavailableError).retryAfter).toBeUndefined();
      return true;
    });
  });

  it('flattens validation errors into the message', async () => {
    const client = clientWith([
      jsonResponse(
        {
          detail: [
            { loc: ['body', 'names'], msg: 'field required', type: 'missing' },
            { loc: ['query', 'q'], msg: 'too long', type: 'value_error' },
          ],
        },
        422,
      ),
    ]);

    await expect(client.ruleSets.list()).rejects.toSatisfy((error: unknown) => {
      const validation = error as UnprocessableEntityError;
      expect(validation.detail).toContain('names: field required');
      expect(validation.detail).toContain('query.q: too long');
      // The structured body stays reachable for callers that want the raw errors.
      expect(Array.isArray((validation.body as { detail: unknown[] }).detail)).toBe(true);
      return true;
    });
  });

  it('does not crash on a non-JSON error body', async () => {
    const client = clientWith([
      new Response('<html>Bad Gateway</html>', {
        status: 502,
        headers: { 'content-type': 'text/html' },
      }),
    ]);

    await expect(client.ruleSets.list()).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ServerError);
      expect((error as ServerError).statusCode).toBe(502);
      return true;
    });
  });

  it('decodes an empty success body as null', async () => {
    const client = clientWith([new Response(null, { status: 204 })]);
    await expect(client.ruleSets.list()).resolves.toBeNull();
  });
});
