export const makeWASocket = (() => {
  let currentImpl = (() => {
    const EventEmitter = (() => {
      function EE() {
        this._events = {};
      }
      EE.prototype.on = function (event, fn) {
        (this._events[event] = this._events[event] || []).push(fn);
        return this;
      };
      EE.prototype.emit = function (event, ...args) {
        (this._events[event] || []).forEach((fn) => fn(...args));
        return true;
      };
      EE.prototype.removeAllListeners = function (event) {
        if (event) delete this._events[event];
        else this._events = {};
        return this;
      };
      EE.prototype.listenerCount = function (event) {
        return (this._events[event] || []).length;
      };
      return EE;
    })();

    function createDefaultSocket() {
      const socket = {
        ev: new EventEmitter(),
        user: { id: '1234567890@s.whatsapp.net', name: 'Test User' },
        sendMessage: (() => {
          const fn = async () => ({
            key: { id: 'msg_test_1', remoteJid: '1234567890@s.whatsapp.net', fromMe: true },
            messageTimestamp: 1234567890,
          });
          return fn;
        })(),
        sendPresenceUpdate: async () => {},
        readMessages: async () => {},
        groupFetchAllParticipating: async () => ({}),
        groupCreate: async () => ({ id: 'newgroup@g.us' }),
        groupUpdateSubject: async () => {},
        groupUpdateDescription: async () => {},
        groupMetadata: async () => ({
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
        groupInviteCode: async () => 'ABC123',
        groupRevokeInvite: async () => 'XYZ789',
        groupAcceptInvite: async () => 'acceptedgroup@g.us',
        groupGetInviteInfo: async () => ({
          id: 'invitedgroup@g.us',
          subject: 'Invited Group',
          creation: 1234567890,
          size: 3,
        }),
        groupParticipantsUpdate: async () => [{ status: '200', id: '9876543210@s.whatsapp.net' }],
        groupSettingUpdate: async () => {},
        groupToggleEphemeral: async () => {},
        groupLeave: async () => {},
        chatModify: async () => {},
        updateBlockStatus: async () => {},
        updateProfileName: async () => {},
        updateProfileStatus: async () => {},
        profilePictureUrl: async () => 'https://example.com/pic.jpg',
        onWhatsApp: async () => [{ jid: '1234567890@s.whatsapp.net', exists: true }],
        updateProfilePicture: async () => {},
        removeProfilePicture: async () => {},
        fetchChatHistory: async () => [],
        logout: async () => {},
        fetchPrivacySettings: async () => ({
          readreceipts: 'all',
          profile: 'contacts',
          status: 'all',
          online: 'all',
          last: 'all',
          groupadd: 'all',
        }),
        updatePrivacySettings: async () => {},
        ws: { close: () => {} },
      };
      return socket;
    }

    const impl = async () => createDefaultSocket();
    impl._createSocket = createDefaultSocket;
    impl._EventEmitter = EventEmitter;
    return impl;
  })();
  return currentImpl;
})();

export const useMultiFileAuthState = async () => ({
  state: { creds: { registered: true }, keys: new Map() },
  saveCreds: async () => {},
});

export const fetchLatestBaileysVersion = async () => ({ version: '1.0.0' });

export const makeCacheableSignalKeyStore = (keys) => keys;

export const isJidGroup = (jid) => String(jid || '').endsWith('@g.us');

export const generateWAMessageFromContent = () => ({});

export const DisconnectReason = {
  LoggedOut: 440,
  ConnectionClosed: 428,
  ConnectionReplaced: 405,
  TimedOut: 408,
  ConnectionLost: 406,
};

export const MessageType = {
  text: 'conversation',
  image: 'imageMessage',
  video: 'videoMessage',
  audio: 'audioMessage',
  document: 'documentMessage',
  sticker: 'stickerMessage',
  location: 'locationMessage',
  contact: 'contactMessage',
  contactsArray: 'contactsArrayMessage',
  extendedText: 'extendedTextMessage',
  buttonsResponse: 'buttonsResponseMessage',
  listResponse: 'listResponseMessage',
  templateButtonReply: 'templateButtonReplyMessage',
  templateButtonReplyHydrated: 'templateButtonReplyHydratedMessage',
};

export default makeWASocket;
