// src/utils/jwt.ts

export interface DecodedToken {
  sub: string;
  exp: number;
  iat?: number;
  [key: string]: any;
}

function base64UrlDecode(input: string): string {
  const base64 = input.replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64.padEnd(base64.length + (4 - (base64.length % 4)) % 4, '=');
  const decoded = atob(padded);
  return decoded;
}

export function decodeToken(token: string): DecodedToken | null {
  try {
    const [, payload] = token.split('.');
    if (!payload) throw new Error('Invalid token format');
    const decodedPayload = JSON.parse(base64UrlDecode(payload));
    return decodedPayload as DecodedToken;
  } catch (e) {
    console.error('Failed to decode JWT:', e);
    return null;
  }
}
