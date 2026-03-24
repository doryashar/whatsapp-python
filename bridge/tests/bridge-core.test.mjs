import { describe, it, expect, vi, beforeAll, beforeEach, afterAll, afterEach } from 'vitest';

process.env.AUTO_LOGIN = 'false';
process.env.DEBUG = 'false';

const {
  mockSocket,
  mockMakeWASocket,
  mockSaveCreds,
  mockUseMultiFileAuthState,
  mockFsExistsSync,
  mockFsMkdirSync,
  mockFsRmSync,
  getJsonLines,
  clearOutput,
  restoreStdout,
  sendToStdin,
  waitForOutput,
  findResponseById,
  findEventByMethod,
} = vi.hoisted(() => {
  const outputLines = [];
  const origWrite = process.stdout.write;

  process.stdout.write = (chunk, ...args) => {
    if (chunk != null) outputLines.push(String(chunk));
    return true;
  };

  function createEmitter() {
    const listeners = {};
    return {
      on(event, handler) {
        if (!listeners[event]) listeners[event] = [];
        listeners[event].push(handler);
        return this;
      },
      emit(event, ...args) {
        const handlers = listeners[event] || [];
        for (const handler of handlers) {
          try {
            handler(...args);
          } catch (e) { /* swallow */ }
        }
        return true;
      },
      removeAllListeners(event) {
        if (event) {
          delete listeners[event];
        } else {
          Object.keys(listeners).forEach((k) => delete listeners[k]);
        }
        return this;
      },
      listenerCount(event) {
        return (listeners[event] || []).length;
      },
    };
  }

  const ev = createEmitter();
  const mockSocket = {
    ev,
    user: { id: '1234567890@s.whatsapp.net', name: 'Test User' },
    sendMessage: vi.fn().mockResolvedValue({
      key: { id: 'msg_test_1', remoteJid: '1234567890@s.whatsapp.net', fromMe: true },
      messageTimestamp: 1234567890,
    }),
    sendPresenceUpdate: vi.fn().mockResolvedValue(undefined),
    readMessages: vi.fn().mockResolvedValue(undefined),
    groupFetchAllParticipating: vi.fn().mockResolvedValue({}),
    groupCreate: vi.fn().mockResolvedValue({ id: 'newgroup@g.us', participants: ['12345@s.whatsapp.net'] }),
    groupUpdateSubject: vi.fn().mockResolvedValue(undefined),
    groupUpdateDescription: vi.fn().mockResolvedValue(undefined),
    groupMetadata: vi.fn().mockResolvedValue({
      subject: 'Test Group',
      subjectOwner: '1234567890@s.whatsapp.net',
      subjectTime: 1234567890,
      creation: 1234567890,
      owner: '1234567890@s.whatsapp.net',
      desc: 'Test description',
      descId: 'desc_123',
      restrict: false,
      announce: false,
      size: 5,
      participants: [
        { id: '1234567890@s.whatsapp.net', admin: 'superadmin' },
        { id: '9876543210@s.whatsapp.net', admin: null },
      ],
    }),
    groupInviteCode: vi.fn().mockResolvedValue('ABC123'),
    groupRevokeInvite: vi.fn().mockResolvedValue('XYZ789'),
    groupAcceptInvite: vi.fn().mockResolvedValue('joinedgroup@g.us'),
    groupGetInviteInfo: vi.fn().mockResolvedValue({
      id: 'invitedgroup@g.us',
      subject: 'Invited Group',
      creation: 1234567890,
      size: 3,
    }),
    groupParticipantsUpdate: vi.fn().mockResolvedValue([
      { status: '200', id: '9876543210@s.whatsapp.net' },
    ]),
    groupSettingUpdate: vi.fn().mockResolvedValue(undefined),
    groupToggleEphemeral: vi.fn().mockResolvedValue(undefined),
    groupLeave: vi.fn().mockResolvedValue(undefined),
    chatModify: vi.fn().mockResolvedValue(undefined),
    updateBlockStatus: vi.fn().mockResolvedValue(undefined),
    updateProfileName: vi.fn().mockResolvedValue(undefined),
    updateProfileStatus: vi.fn().mockResolvedValue(undefined),
    profilePictureUrl: vi.fn().mockResolvedValue('https://example.com/pic.jpg'),
    onWhatsApp: vi.fn().mockResolvedValue([{ jid: '1234567890@s.whatsapp.net', exists: true }]),
    updateProfilePicture: vi.fn().mockResolvedValue(undefined),
    removeProfilePicture: vi.fn().mockResolvedValue(undefined),
    fetchChatHistory: vi.fn().mockResolvedValue([]),
    logout: vi.fn().mockResolvedValue(undefined),
    fetchPrivacySettings: vi.fn().mockResolvedValue({
      readreceipts: 'all', profile: 'contacts', status: 'all',
      online: 'all', last: 'all', groupadd: 'all',
    }),
    updatePrivacySettings: vi.fn().mockResolvedValue(undefined),
    ws: { close: vi.fn() },
  };

  const mockMakeWASocket = vi.fn(() => mockSocket);
  const mockSaveCreds = vi.fn().mockResolvedValue(undefined);
  const mockUseMultiFileAuthState = vi.fn(() =>
    Promise.resolve({
      state: { creds: { registered: true }, keys: new Map() },
      saveCreds: mockSaveCreds,
    })
  );

  const mockFsExistsSync = vi.fn(() => false);
  const mockFsMkdirSync = vi.fn();
  const mockFsRmSync = vi.fn();

  function getJsonLines() {
    return outputLines.join('').split('\n').filter(Boolean).map((l) => {
      try { return JSON.parse(l); } catch { return null; }
    }).filter(Boolean);
  }
  function clearOutput() { outputLines.length = 0; }
  function restoreStdout() { process.stdout.write = origWrite; }
  function sendToStdin(data) {
    const str = typeof data === 'string' ? data : JSON.stringify(data);
    process.stdin.emit('data', str + '\n');
  }
  async function waitForOutput(ms = 100) {
    await new Promise((r) => setTimeout(r, ms));
  }
  function findResponseById(id) {
    return getJsonLines().find((l) => l.id === id);
  }
  function findEventByMethod(method) {
    return getJsonLines().filter((l) => l.method === method && l.id === undefined);
  }

  return {
    mockSocket, mockMakeWASocket, mockSaveCreds, mockUseMultiFileAuthState,
    mockFsExistsSync, mockFsMkdirSync, mockFsRmSync,
    getJsonLines, clearOutput, restoreStdout, sendToStdin, waitForOutput,
    findResponseById, findEventByMethod,
  };
});

vi.mock('@whiskeysockets/baileys', () => ({
  makeWASocket: mockMakeWASocket,
  useMultiFileAuthState: mockUseMultiFileAuthState,
  fetchLatestBaileysVersion: vi.fn(() => Promise.resolve({ version: '1.0.0' })),
  makeCacheableSignalKeyStore: vi.fn((keys) => keys),
  isJidGroup: vi.fn((jid) => String(jid || '').endsWith('@g.us')),
  generateWAMessageFromContent: vi.fn(),
  DisconnectReason: { loggedOut: 440, LoggedOut: 440 },
}));

vi.mock('pino', () => {
  const noop = vi.fn();
  const mockPino = vi.fn(() => ({
    info: noop, debug: noop, error: noop, warn: noop, fatal: noop, trace: noop,
    child: () => ({ info: noop, debug: noop, error: noop, warn: noop, fatal: noop, trace: noop }),
  }));
  mockPino.destination = vi.fn(() => ({}));
  return { default: mockPino };
});

vi.mock('qrcode', () => ({
  default: { toDataURL: vi.fn(() => Promise.resolve('data:image/png;base64,xxx')) },
  toDataURL: vi.fn(() => Promise.resolve('data:image/png;base64,xxx')),
}));

vi.mock('fs', () => {
  const fsMock = {
    existsSync: mockFsExistsSync,
    mkdirSync: mockFsMkdirSync,
    readFileSync: vi.fn(() => Buffer.from('fake-data')),
    writeFileSync: vi.fn(),
    readdirSync: vi.fn(() => []),
    statSync: vi.fn(() => ({ mtimeMs: Date.now() - 3600000 })),
    rmSync: mockFsRmSync,
  };
  return { __esModule: true, default: fsMock, ...fsMock };
});

import '../index.mjs';

async function sendRequest(id, method, params = {}) {
  clearOutput();
  sendToStdin({ jsonrpc: '2.0', id, method, params });
  await waitForOutput();
  const lines = getJsonLines();
  return findResponseById(id);
}

let isConnected = false;

async function doLogin() {
  if (isConnected) return;
  clearOutput();
  sendToStdin({ jsonrpc: '2.0', id: 'login', method: 'login' });
  await waitForOutput(300);
  mockSocket.ev.emit('connection.update', { connection: 'open' });
  await waitForOutput(200);
  isConnected = true;
}

async function doDisconnect() {
  if (!isConnected) return;
  mockSocket.ev.emit('connection.update', {
    connection: 'close',
    lastDisconnect: { error: { output: { statusCode: 408 }, message: 'Test reset' } },
  });
  await waitForOutput(100);
  isConnected = false;
  clearOutput();
}

describe('Bridge Core', () => {
  beforeEach(() => {
    clearOutput();
  });

  afterAll(() => {
    restoreStdout();
  });

  describe('Startup', () => {
    it('should report disconnected status initially', async () => {
      const resp = await sendRequest(1, 'get_status');
      expect(resp).toBeDefined();
      expect(resp.result.connection_state).toBe('disconnected');
    });

    it('should return null self_id when disconnected', async () => {
      const resp = await sendRequest(2, 'self_id');
      expect(resp).toBeDefined();
      expect(resp.result.jid).toBeNull();
    });

    it('should return auth_exists as false by default', async () => {
      const resp = await sendRequest(3, 'auth_exists');
      expect(resp).toBeDefined();
      expect(resp.result.exists).toBe(false);
    });

    it('should return auth_age as null when no creds', async () => {
      const resp = await sendRequest(4, 'auth_age');
      expect(resp).toBeDefined();
      expect(resp.result.age_ms).toBeNull();
    });

    it('should return settings with defaults', async () => {
      const resp = await sendRequest(5, 'get_settings');
      expect(resp).toBeDefined();
      expect(resp.result).toHaveProperty('reject_call');
      expect(resp.result).toHaveProperty('always_online');
    });

    it('should update and return settings', async () => {
      const resp = await sendRequest(6, 'update_settings', { reject_call: true });
      expect(resp).toBeDefined();
      expect(resp.result.reject_call).toBe(true);
    });

  });

  describe('Login flow', () => {
    it('should create socket on login', async () => {
      await doLogin();
      expect(mockMakeWASocket).toHaveBeenCalled();
      expect(mockUseMultiFileAuthState).toHaveBeenCalled();
      expect(mockFsMkdirSync).toHaveBeenCalled();
    });

    it('should return connected status after login', async () => {
      expect(isConnected).toBe(true);
      const resp = await sendRequest(10, 'get_status');
      expect(resp).toBeDefined();
      expect(resp.result.connection_state).toBe('connected');
      expect(resp.result.self.jid).toBe('1234567890@s.whatsapp.net');
    });

    it('should return self info after connection', async () => {
      const resp = await sendRequest(11, 'self_id');
      expect(resp).toBeDefined();
      expect(resp.result.jid).toBe('1234567890@s.whatsapp.net');
      expect(resp.result.e164).toBe('1234567890');
      expect(resp.result.name).toBe('Test User');
    });

    it('should return already_connected on second login', async () => {
      const resp = await sendRequest(12, 'login');
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('already_connected');
    });

    it('should emit connecting event then restore connected state', async () => {
      clearOutput();
      mockSocket.ev.emit('connection.update', { connection: 'connecting' });
      await waitForOutput();
      const events = findEventByMethod('connecting');
      expect(events.length).toBeGreaterThanOrEqual(1);
      mockSocket.ev.emit('connection.update', { connection: 'open' });
      await waitForOutput(100);
    });
  });

  describe('Messaging', () => {
    it('send_message text should call sock.sendMessage', async () => {
      mockSocket.sendMessage.mockClear();
      const resp = await sendRequest(20, 'send_message', { to: '1234567890', text: 'hello' });
      expect(resp).toBeDefined();
      expect(resp.result.message_id).toBe('msg_test_1');
      expect(resp.result.to).toBe('1234567890@s.whatsapp.net');
      expect(mockSocket.sendMessage).toHaveBeenCalledWith(
        '1234567890@s.whatsapp.net',
        expect.objectContaining({ text: 'hello' })
      );
    });

    it('send_message with quoted should include contextInfo', async () => {
      mockSocket.sendMessage.mockClear();
      await sendRequest(21, 'send_message', {
        to: '1234567890', text: 'reply',
        quoted: { message_id: 'abc123', chat: '1234567890@s.whatsapp.net', text: 'original' },
      });
      const callArgs = mockSocket.sendMessage.mock.calls[0];
      expect(callArgs[1].contextInfo).toBeDefined();
      expect(callArgs[1].contextInfo.stanzaId).toBe('abc123');
    });

    it('send_message should convert phone to jid', async () => {
      mockSocket.sendMessage.mockClear();
      await sendRequest(22, 'send_message', { to: '9876543210', text: 'test' });
      expect(mockSocket.sendMessage.mock.calls[0][0]).toBe('9876543210@s.whatsapp.net');
    });

    it('send_message should convert group id to jid', async () => {
      mockSocket.sendMessage.mockClear();
      await sendRequest(23, 'send_message', { to: '12345-67890', text: 'group msg' });
      expect(mockSocket.sendMessage.mock.calls[0][0]).toBe('12345-67890@g.us');
    });

    it('send_message not connected should throw', async () => {
      await doDisconnect();
      const resp = await sendRequest(24, 'send_message', { to: '123', text: 'hello' });
      expect(resp.error).toBeDefined();
      expect(resp.error.message).toBe('Not connected to WhatsApp');
      await doLogin();
    });

    it('send_reaction should call sendMessage with react', async () => {
      mockSocket.sendMessage.mockClear();
      const resp = await sendRequest(25, 'send_reaction', {
        chat: '1234567890', message_id: 'msg_1', emoji: '\u{1F44D}',
      });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('reacted');
      expect(mockSocket.sendMessage).toHaveBeenCalled();
      const callArgs = mockSocket.sendMessage.mock.calls[0];
      expect(callArgs[1].react.text).toBe('\u{1F44D}');
    });

    it('send_typing should call sendPresenceUpdate', async () => {
      mockSocket.sendPresenceUpdate.mockClear();
      const resp = await sendRequest(26, 'send_typing', { to: '1234567890' });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('typing');
      expect(mockSocket.sendPresenceUpdate).toHaveBeenCalledWith('composing', '1234567890@s.whatsapp.net');
    });

    it('edit_message should call sendMessage with edit', async () => {
      mockSocket.sendMessage.mockClear();
      const resp = await sendRequest(27, 'edit_message', {
        to: '1234567890', message_id: 'msg_1', text: 'edited',
      });
      expect(resp).toBeDefined();
      expect(resp.result.message_id).toBeDefined();
      const callArgs = mockSocket.sendMessage.mock.calls[0];
      expect(callArgs[1].edit.id).toBe('msg_1');
    });

    it('delete_message should call sendMessage with delete', async () => {
      mockSocket.sendMessage.mockClear();
      const resp = await sendRequest(28, 'delete_message', { to: '1234567890', message_id: 'msg_1' });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('deleted');
      const callArgs = mockSocket.sendMessage.mock.calls[0];
      expect(callArgs[1].delete.id).toBe('msg_1');
    });

    it('mark_read should call readMessages', async () => {
      mockSocket.readMessages.mockClear();
      const resp = await sendRequest(29, 'mark_read', { to: '1234567890', message_ids: ['m1', 'm2'] });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('read');
      expect(resp.result.count).toBe(2);
      expect(mockSocket.readMessages).toHaveBeenCalledWith([
        { remoteJid: '1234567890@s.whatsapp.net', id: 'm1', fromMe: false },
        { remoteJid: '1234567890@s.whatsapp.net', id: 'm2', fromMe: false },
      ]);
    });
  });

  describe('Group operations', () => {
    it('group_create should call sock.groupCreate', async () => {
      mockSocket.groupCreate.mockClear();
      const resp = await sendRequest(30, 'group_create', {
        subject: 'Test Group', participants: ['1234567890', '9876543210'],
      });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('created');
      expect(resp.result.group_jid).toBe('newgroup@g.us');
      expect(mockSocket.groupCreate).toHaveBeenCalledWith(
        'Test Group', ['1234567890@s.whatsapp.net', '9876543210@s.whatsapp.net']
      );
    });

    it('group_update_subject should call sock.groupUpdateSubject', async () => {
      mockSocket.groupUpdateSubject.mockClear();
      const resp = await sendRequest(31, 'group_update_subject', {
        group_jid: '12345-67890', subject: 'New Subject',
      });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('updated');
      expect(mockSocket.groupUpdateSubject).toHaveBeenCalledWith('12345-67890@g.us', 'New Subject');
    });

    it('group_update_description should call sock.groupUpdateDescription', async () => {
      mockSocket.groupUpdateDescription.mockClear();
      const resp = await sendRequest(32, 'group_update_description', {
        group_jid: '12345-67890', description: 'New desc',
      });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('updated');
      expect(mockSocket.groupUpdateDescription).toHaveBeenCalledWith('12345-67890@g.us', 'New desc');
    });

    it('group_get_info should return metadata', async () => {
      mockSocket.groupMetadata.mockClear();
      const resp = await sendRequest(33, 'group_get_info', { group_jid: '12345-67890' });
      expect(resp).toBeDefined();
      expect(resp.result.subject).toBe('Test Group');
      expect(resp.result.size).toBe(5);
      expect(resp.result.participants).toHaveLength(2);
      expect(mockSocket.groupMetadata).toHaveBeenCalledWith('12345-67890@g.us');
    });

    it('group_get_all should return groups', async () => {
      const resp = await sendRequest(34, 'group_get_all');
      expect(resp).toBeDefined();
      expect(resp.result.groups).toBeDefined();
    });

    it('group_get_invite_code should return code', async () => {
      mockSocket.groupInviteCode.mockClear();
      const resp = await sendRequest(35, 'group_get_invite_code', { group_jid: '12345-67890' });
      expect(resp).toBeDefined();
      expect(resp.result.invite_code).toBe('ABC123');
      expect(mockSocket.groupInviteCode).toHaveBeenCalledWith('12345-67890@g.us');
    });

    it('group_revoke_invite should return new code', async () => {
      mockSocket.groupRevokeInvite.mockClear();
      const resp = await sendRequest(36, 'group_revoke_invite', { group_jid: '12345-67890' });
      expect(resp).toBeDefined();
      expect(resp.result.new_invite_code).toBe('XYZ789');
    });

    it('group_accept_invite should return group jid', async () => {
      mockSocket.groupAcceptInvite.mockClear();
      const resp = await sendRequest(37, 'group_accept_invite', { invite_code: 'ABC123' });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('joined');
      expect(resp.result.group_jid).toBe('joinedgroup@g.us');
    });

    it('group_leave should call sock.groupLeave', async () => {
      mockSocket.groupLeave.mockClear();
      const resp = await sendRequest(38, 'group_leave', { group_jid: '12345-67890' });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('left');
      expect(mockSocket.groupLeave).toHaveBeenCalledWith('12345-67890@g.us');
    });

    it('group_update_participant should call groupParticipantsUpdate', async () => {
      mockSocket.groupParticipantsUpdate.mockClear();
      const resp = await sendRequest(39, 'group_update_participant', {
        group_jid: '12345-67890', action: 'add', participants: ['9876543210'],
      });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('updated');
      expect(mockSocket.groupParticipantsUpdate).toHaveBeenCalledWith(
        '12345-67890@g.us', ['9876543210@s.whatsapp.net'], 'add'
      );
    });

    it('group_get_invite_info should return info', async () => {
      mockSocket.groupGetInviteInfo.mockClear();
      const resp = await sendRequest(40, 'group_get_invite_info', { invite_code: 'ABC123' });
      expect(resp).toBeDefined();
      expect(resp.result.subject).toBe('Invited Group');
    });
  });

  describe('Contact & Chat operations', () => {
    it('get_contacts should return contacts from store', async () => {
      const resp = await sendRequest(41, 'get_contacts');
      expect(resp).toBeDefined();
      expect(resp.result.contacts).toEqual([]);
    });

    it('get_contacts should throw when not connected', async () => {
      await doDisconnect();
      const resp = await sendRequest(42, 'get_contacts');
      expect(resp.error).toBeDefined();
      expect(resp.error.message).toBe('Not connected to WhatsApp');
      await doLogin();
    });

    it('archive_chat should call sock.chatModify', async () => {
      mockSocket.chatModify.mockClear();
      const resp = await sendRequest(43, 'archive_chat', { chat_jid: '1234567890', archive: true });
      expect(resp).toBeDefined();
      expect(resp.result.archived).toBe(true);
      expect(mockSocket.chatModify).toHaveBeenCalledWith({ archive: true }, '1234567890@s.whatsapp.net');
    });

    it('block_user should call updateBlockStatus', async () => {
      mockSocket.updateBlockStatus.mockClear();
      const resp = await sendRequest(44, 'block_user', { jid: '1234567890', block: true });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('blocked');
      expect(mockSocket.updateBlockStatus).toHaveBeenCalledWith('1234567890@s.whatsapp.net', 'block');
    });

    it('block_user with block=false should unblock', async () => {
      mockSocket.updateBlockStatus.mockClear();
      const resp = await sendRequest(45, 'block_user', { jid: '1234567890', block: false });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('unblocked');
      expect(mockSocket.updateBlockStatus).toHaveBeenCalledWith('1234567890@s.whatsapp.net', 'unblock');
    });
  });

  describe('Profile operations', () => {
    it('update_profile_name should call sock.updateProfileName', async () => {
      mockSocket.updateProfileName.mockClear();
      const resp = await sendRequest(50, 'update_profile_name', { name: 'New Name' });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('updated');
      expect(mockSocket.updateProfileName).toHaveBeenCalledWith('New Name');
    });

    it('update_profile_status should call sock.updateProfileStatus', async () => {
      mockSocket.updateProfileStatus.mockClear();
      const resp = await sendRequest(51, 'update_profile_status', { status: 'Hey there!' });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('updated');
      expect(mockSocket.updateProfileStatus).toHaveBeenCalledWith('Hey there!');
    });

    it('get_profile_picture should call sock.profilePictureUrl', async () => {
      mockSocket.profilePictureUrl.mockClear();
      const resp = await sendRequest(52, 'get_profile_picture', { jid: '1234567890' });
      expect(resp).toBeDefined();
      expect(resp.result.url).toBe('https://example.com/pic.jpg');
      expect(mockSocket.profilePictureUrl).toHaveBeenCalledWith('1234567890', 'image');
    });

    it('get_profile should call sock.onWhatsApp', async () => {
      mockSocket.onWhatsApp.mockClear();
      const resp = await sendRequest(53, 'get_profile', { jid: '1234567890' });
      expect(resp).toBeDefined();
      expect(resp.result.exists).toBe(true);
      expect(mockSocket.onWhatsApp).toHaveBeenCalledWith('1234567890@s.whatsapp.net');
    });

    it('check_whatsapp should check multiple numbers', async () => {
      mockSocket.onWhatsApp.mockClear();
      const resp = await sendRequest(54, 'check_whatsapp', { numbers: ['1234567890', '9876543210'] });
      expect(resp).toBeDefined();
      expect(resp.result.results).toHaveLength(2);
      expect(resp.result.results[0].exists).toBe(true);
    });
  });

  describe('Privacy settings', () => {
    it('fetch_privacy_settings should call sock.fetchPrivacySettings', async () => {
      mockSocket.fetchPrivacySettings.mockClear();
      const resp = await sendRequest(55, 'fetch_privacy_settings');
      expect(resp).toBeDefined();
      expect(resp.result.readreceipts).toBe('all');
      expect(resp.result.profile).toBe('contacts');
      expect(mockSocket.fetchPrivacySettings).toHaveBeenCalled();
    });

    it('update_privacy_settings should call sock.updatePrivacySettings', async () => {
      mockSocket.updatePrivacySettings.mockClear();
      const resp = await sendRequest(56, 'update_privacy_settings', {
        readreceipts: 'none', profile: 'contacts',
      });
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('updated');
      expect(mockSocket.updatePrivacySettings).toHaveBeenCalledWith({
        readreceipts: 'none', profile: 'contacts',
      });
    });
  });

  describe('Disconnection', () => {
    it('should emit disconnected event on connection close', async () => {
      clearOutput();
      mockSocket.ev.emit('connection.update', {
        connection: 'close',
        lastDisconnect: { error: { output: { statusCode: 428 }, message: 'Connection closed' } },
      });
      await waitForOutput();
      const events = findEventByMethod('disconnected');
      expect(events.length).toBeGreaterThanOrEqual(1);
      expect(events[0].params.reason).toBe(428);
    });

    it('should clear auth dir on loggedOut disconnect', async () => {
      await doLogin();
      mockFsRmSync.mockClear();
      clearOutput();
      mockSocket.ev.emit('connection.update', {
        connection: 'close',
        lastDisconnect: { error: { output: { statusCode: 440 }, message: 'Logged out' } },
      });
      await waitForOutput();
      expect(mockFsRmSync).toHaveBeenCalled();
      isConnected = false;
    });

    it('should report disconnected status after close', async () => {
      const resp = await sendRequest(60, 'get_status');
      expect(resp).toBeDefined();
      expect(resp.result.connection_state).toBe('disconnected');
      expect(resp.result.self).toBeNull();
    });
  });

  describe('Auth state saving', () => {
    it('should call saveCreds on creds.update event', async () => {
      await doLogin();
      mockSaveCreds.mockClear();
      clearOutput();
      mockSocket.ev.emit('creds.update');
      await waitForOutput();
      expect(mockSaveCreds).toHaveBeenCalled();
      const events = findEventByMethod('auth.update');
      expect(events.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('Message events', () => {
    it('should emit message event on incoming messages.upsert', async () => {
      clearOutput();
      mockSocket.ev.emit('messages.upsert', {
        type: 'notify',
        messages: [{
          key: { id: 'incoming_1', remoteJid: '9876543210@s.whatsapp.net', fromMe: false },
          message: { conversation: 'Hello!' },
          pushName: 'Sender',
          messageTimestamp: 1700000000,
        }],
      });
      await waitForOutput();
      const events = findEventByMethod('message');
      expect(events.length).toBeGreaterThanOrEqual(1);
      expect(events[0].params.text).toBe('Hello!');
      expect(events[0].params.from).toBe('9876543210@s.whatsapp.net');
    });

    it('should ignore own messages', async () => {
      clearOutput();
      mockSocket.ev.emit('messages.upsert', {
        type: 'notify',
        messages: [{
          key: { id: 'own_1', remoteJid: '9876543210@s.whatsapp.net', fromMe: true },
          message: { conversation: 'My msg' },
          messageTimestamp: 1700000000,
        }],
      });
      await waitForOutput();
      expect(findEventByMethod('message')).toHaveLength(0);
    });

    it('should emit message_deleted event', async () => {
      clearOutput();
      mockSocket.ev.emit('messages.delete', {
        key: { id: 'del_1', remoteJid: '1234567890@s.whatsapp.net' },
      });
      await waitForOutput();
      const events = findEventByMethod('message_deleted');
      expect(events.length).toBeGreaterThanOrEqual(1);
      expect(events[0].params.message_id).toBe('del_1');
    });

    it('should emit sent event after send_message', async () => {
      await doLogin();
      clearOutput();
      mockSocket.sendMessage.mockClear();
      await sendRequest(70, 'send_message', { to: '1234567890', text: 'hello' });
      const events = findEventByMethod('sent');
      expect(events.length).toBeGreaterThanOrEqual(1);
      expect(events[0].params.type).toBe('text');
    });
  });

  describe('QR handling', () => {
    it('should emit qr event when QR generated', async () => {
      clearOutput();
      mockSocket.ev.emit('connection.update', { qr: 'test-qr-data' });
      await waitForOutput();
      const events = findEventByMethod('qr');
      expect(events.length).toBeGreaterThanOrEqual(1);
      expect(events[0].params.qr).toBe('test-qr-data');
    });
  });

  describe('Logout', () => {
    it('should call sock.logout and clear state', async () => {
      mockSocket.logout.mockClear();
      const resp = await sendRequest(80, 'logout');
      expect(resp).toBeDefined();
      expect(resp.result.status).toBe('logged_out');
      expect(mockSocket.logout).toHaveBeenCalled();
    });
  });

  describe('Reconnection', () => {
    let loginCountBefore;
    beforeAll(async () => {
      isConnected = false;
      await waitForOutput(50);
      loginCountBefore = mockMakeWASocket.mock.calls.length;
    });

    it('should create new socket on login after disconnect', async () => {
      await doLogin();
      expect(mockMakeWASocket.mock.calls.length).toBeGreaterThan(loginCountBefore);
      const resp = await sendRequest(81, 'get_status');
      expect(resp.result.connection_state).toBe('connected');
    });
  });
});
