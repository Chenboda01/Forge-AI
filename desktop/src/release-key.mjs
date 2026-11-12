// Trusted release-signing key for Forge AI Desktop updates.
//
// This is the PUBLIC half of the development key generated for V1.1 testing.
// Public keys are safe to distribute. The matching private key is kept outside
// the repository and is never committed, logged, or bundled.
//
// The fingerprint is the hex-encoded SHA-256 of the DER SubjectPublicKeyInfo.
// Rotating this key requires shipping a new application build that trusts the
// replacement key.

export const RELEASE_KEY_ID = 'forge-desktop-dev-2026-11';
export const RELEASE_KEY_ENVIRONMENT = 'development';

export const RELEASE_PUBLIC_KEY_PEM = `-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA/2cfzZHQl0j+xkFLE1oL4auLrVvxHSD3jsXw16Lpt1Q=
-----END PUBLIC KEY-----
`;

export const RELEASE_KEY_FINGERPRINT_SHA256 =
  'e5bca27ba85dc1b45c6cd59836c57d84f7c9f74c79bf3b26e585fbe58ba47589';
