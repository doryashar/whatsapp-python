import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest';

process.env.AUTO_LOGIN = 'false';
process.env.DEBUG = 'false';

const {
  getJsonLines,
  clearOutput,
  restoreStdout,
  sendToStdin,
  waitForOutput,
} = vi.hoisted(() => {
  const lines = [];
  const origWrite = process.stdout.write;

  process.stdout.write = (chunk, ...args) => {
    if (chunk != null) lines.push(String(chunk));
    return true;
  };

  function getJsonLines() {
    return lines
      .join('')
      .split('\n')
      .filter(Boolean)
      .map((l) => {
        try {
          return JSON.parse(l);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  }

  function clearOutput() {
    lines.length = 0;
  }

  function restoreStdout() {
    process.stdout.write = origWrite;
  }

  function sendToStdin(data) {
    const str = typeof data === 'string' ? data : JSON.stringify(data);
    process.stdin.emit('data', str + '\n');
  }

  async function waitForOutput(ms = 80) {
    await new Promise((r) => setTimeout(r, ms));
  }

  return { getJsonLines, clearOutput, restoreStdout, sendToStdin, waitForOutput };
});

vi.mock('@whiskeysockets/baileys', () => ({
  makeWASocket: vi.fn(),
  useMultiFileAuthState: vi.fn(),
  fetchLatestBaileysVersion: vi.fn(() => Promise.resolve({ version: '1.0.0' })),
  makeCacheableSignalKeyStore: vi.fn((keys) => keys),
  isJidGroup: vi.fn(() => false),
  generateWAMessageFromContent: vi.fn(),
  DisconnectReason: { LoggedOut: 440 },
}));

vi.mock('pino', () => {
  const noop = vi.fn();
  const mockPino = vi.fn(() => ({
    info: noop,
    debug: noop,
    error: noop,
    warn: noop,
    fatal: noop,
    trace: noop,
    child: () => ({ info: noop, debug: noop, error: noop, warn: noop, fatal: noop, trace: noop }),
  }));
  mockPino.destination = vi.fn(() => ({}));
  return {
    default: mockPino,
  };
});

vi.mock('qrcode', () => ({
  default: { toDataURL: vi.fn(() => Promise.resolve('data:image/png;base64,xxx')) },
  toDataURL: vi.fn(() => Promise.resolve('data:image/png;base64,xxx')),
}));

vi.mock('fs', () => {
  const fsMock = {
    existsSync: vi.fn(() => false),
    mkdirSync: vi.fn(),
    readFileSync: vi.fn(() => Buffer.from('')),
    writeFileSync: vi.fn(),
    readdirSync: vi.fn(() => []),
    statSync: vi.fn(),
    rmSync: vi.fn(),
  };
  fsMock.default = fsMock;
  return fsMock;
});

import '../index.mjs';

describe('JSON-RPC Protocol', () => {
  let initialOutput;

  beforeAll(() => {
    initialOutput = getJsonLines();
  });

  beforeEach(() => {
    clearOutput();
  });

  afterAll(() => {
    restoreStdout();
  });

  it('should parse a valid JSON-RPC request and return a response with result', async () => {
    sendToStdin({ jsonrpc: '2.0', id: 1, method: 'get_status' });
    await waitForOutput();

    const jsonLines = getJsonLines();
    const response = jsonLines.find((l) => l.id === 1);

    expect(response).toBeDefined();
    expect(response.jsonrpc).toBe('2.0');
    expect(response.id).toBe(1);
    expect(response).toHaveProperty('result');
    expect(response).not.toHaveProperty('error');
  });

  it('should parse a valid JSON-RPC notification (no id) and not send a response', async () => {
    sendToStdin({ jsonrpc: '2.0', method: 'get_status' });
    await waitForOutput();

    const jsonLines = getJsonLines();
    const responses = jsonLines.filter((l) => l.id !== undefined);
    expect(responses).toHaveLength(0);
  });

  it('should ignore non-JSON lines (pino output etc.)', async () => {
    sendToStdin('[2024-01-01 12:00:00] INFO: something happened');
    await waitForOutput();

    const jsonLines = getJsonLines();
    expect(jsonLines).toHaveLength(0);
  });

  it('should handle malformed JSON gracefully without crashing', async () => {
    sendToStdin('{invalid json');
    await waitForOutput();

    const jsonLines = getJsonLines();
    expect(jsonLines).toHaveLength(0);
  });

  it('should reject requests without jsonrpc "2.0" with Invalid Request error', async () => {
    sendToStdin({ jsonrpc: '1.0', id: 2, method: 'get_status' });
    await waitForOutput();

    const jsonLines = getJsonLines();
    const response = jsonLines.find((l) => l.id === 2);

    expect(response).toBeDefined();
    expect(response.jsonrpc).toBe('2.0');
    expect(response.id).toBe(2);
    expect(response.error).toBeDefined();
    expect(response.error.code).toBe(-32600);
    expect(response.error.message).toBe('Invalid Request');
  });

  it('should reject requests without a method field with Invalid Request error', async () => {
    sendToStdin({ jsonrpc: '2.0', id: 3, params: {} });
    await waitForOutput();

    const jsonLines = getJsonLines();
    const response = jsonLines.find((l) => l.id === 3);

    expect(response).toBeDefined();
    expect(response.error).toBeDefined();
    expect(response.error.code).toBe(-32600);
    expect(response.error.message).toBe('Invalid Request');
  });

  it('should return Method not found error for unknown methods', async () => {
    sendToStdin({ jsonrpc: '2.0', id: 4, method: 'nonexistent_method' });
    await waitForOutput();

    const jsonLines = getJsonLines();
    const response = jsonLines.find((l) => l.id === 4);

    expect(response).toBeDefined();
    expect(response.jsonrpc).toBe('2.0');
    expect(response.id).toBe(4);
    expect(response.error).toBeDefined();
    expect(response.error.code).toBe(-32601);
    expect(response.error.message).toBe('Method not found');
  });

  it('should return error response when method throws', async () => {
    sendToStdin({
      jsonrpc: '2.0',
      id: 5,
      method: 'send_message',
      params: { to: '1234567890', text: 'hello' },
    });
    await waitForOutput();

    const jsonLines = getJsonLines();
    const response = jsonLines.find((l) => l.id === 5);

    expect(response).toBeDefined();
    expect(response.jsonrpc).toBe('2.0');
    expect(response.id).toBe(5);
    expect(response.error).toBeDefined();
    expect(response.error.code).toBe(-32000);
    expect(response.error.message).toBe('Not connected to WhatsApp');
  });

  it('should handle concurrent requests with correct id matching', async () => {
    const batch =
      JSON.stringify({ jsonrpc: '2.0', id: 10, method: 'get_status' }) + '\n' +
      JSON.stringify({ jsonrpc: '2.0', id: 20, method: 'get_settings' }) + '\n' +
      JSON.stringify({ jsonrpc: '2.0', id: 30, method: 'auth_exists' }) + '\n';
    process.stdin.emit('data', batch);
    await waitForOutput(200);

    const jsonLines = getJsonLines();
    const r10 = jsonLines.find((l) => l.id === 10);
    const r20 = jsonLines.find((l) => l.id === 20);
    const r30 = jsonLines.find((l) => l.id === 30);

    expect(r10).toBeDefined();
    expect(r10).toHaveProperty('result');
    expect(r10.result).toHaveProperty('connection_state');

    expect(r20).toBeDefined();
    expect(r20).toHaveProperty('result');
    expect(r20.result).toHaveProperty('reject_call');

    expect(r30).toBeDefined();
    expect(r30).toHaveProperty('result');
    expect(r30.result).toHaveProperty('exists');
  });

  it('should send response with result in correct JSON-RPC format', async () => {
    sendToStdin({ jsonrpc: '2.0', id: 42, method: 'self_id' });
    await waitForOutput();

    const jsonLines = getJsonLines();
    const response = jsonLines.find((l) => l.id === 42);

    expect(response).toBeDefined();
    expect(response).toHaveProperty('jsonrpc', '2.0');
    expect(response).toHaveProperty('id', 42);
    expect(response).toHaveProperty('result');
    expect(response).not.toHaveProperty('error');
    expect(response.result).toHaveProperty('jid');
    expect(response.result).toHaveProperty('e164');
    expect(response.result).toHaveProperty('name');
  });

  it('should send event/notification without id field', async () => {
    clearOutput();
    sendToStdin({ jsonrpc: '2.0', id: 99, method: 'get_status' });
    await waitForOutput();

    const jsonLines = getJsonLines();
    const response = jsonLines.find((l) => l.id === 99);
    expect(response).toBeDefined();
    expect(response).toHaveProperty('result');
  });

  it('should handle empty params gracefully', async () => {
    sendToStdin({ jsonrpc: '2.0', id: 7, method: 'get_status' });
    await waitForOutput();

    const jsonLines = getJsonLines();
    const response = jsonLines.find((l) => l.id === 7);

    expect(response).toBeDefined();
    expect(response).toHaveProperty('result');
    expect(response.result).toHaveProperty('connection_state');
  });

  it('should handle params with extra fields without error', async () => {
    sendToStdin({
      jsonrpc: '2.0',
      id: 8,
      method: 'get_status',
      params: { extra: 'field', another: 123 },
    });
    await waitForOutput();

    const jsonLines = getJsonLines();
    const response = jsonLines.find((l) => l.id === 8);

    expect(response).toBeDefined();
    expect(response).toHaveProperty('result');
  });

  it('should not respond to notifications even when method throws', async () => {
    sendToStdin({
      jsonrpc: '2.0',
      method: 'send_message',
      params: { to: '123', text: 'hello' },
    });
    await waitForOutput();

    const jsonLines = getJsonLines();
    expect(jsonLines).toHaveLength(0);
  });

  it('should not respond to invalid requests without id', async () => {
    sendToStdin({ jsonrpc: '1.0', method: 'get_status' });
    await waitForOutput();

    const jsonLines = getJsonLines();
    expect(jsonLines).toHaveLength(0);
  });

  it('should not respond to unknown method notifications', async () => {
    sendToStdin({ jsonrpc: '2.0', method: 'completely_unknown' });
    await waitForOutput();

    const jsonLines = getJsonLines();
    expect(jsonLines).toHaveLength(0);
  });

  it('should emit ready event on bridge startup', () => {
    const readyEvent = initialOutput.find((l) => l.method === 'ready' && l.id === undefined);

    expect(readyEvent).toBeDefined();
    expect(readyEvent.jsonrpc).toBe('2.0');
    expect(readyEvent.params).toHaveProperty('pid');
    expect(typeof readyEvent.params.pid).toBe('number');
  });
});
