# ADR-002: Transport Protocol Signature

- **Status**: Accepted
- **Date**: 2026-01-15

## Context
The hardware requires a specific packet format for all commands (brightness, images, clears). Without the correct signature and padding, the device ignores the data.

## Decision
All transport packets must be exactly **513 bytes** long (512 bytes payload + 1 byte report ID).
The header must start with the ASCII signature `"CRT"`.

Specific command byte offsets:
- `0-2`: `"CRT"`
- `3-5`: Command (e.g., `LIG`, `CLE`, `LOG`)
- `6+`: Command-specific payload.

## Consequences
- **Strict Padding**: Every packet must be Null-padded to exactly 513 bytes.
- **Robustness**: Any mismatch in signature or length will result in a failed hardware operation.
- **Efficiency**: Large image transfers must be segmented into multiple 513-byte packets, which is handled by the `HIDTransport` class.
